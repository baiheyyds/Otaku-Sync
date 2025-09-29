import sys
import os
import json
import asyncio
from functools import partial
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QComboBox, QListWidget, QListWidgetItem, QPushButton, QLabel, QMessageBox, 
    QInputDialog, QLineEdit, QPlainTextEdit, QDialog, QDialogButtonBox, QCheckBox,
    QGroupBox, QGridLayout
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QScreen

from utils.gui_bridge import patch_logger, log_bridge
from core.gui_worker import GameSyncWorker, ScriptWorker
from utils import logger as project_logger
from core.interaction import TYPE_SELECTION_MAP
from core.context_factory import create_shared_context
from core.init import close_context

# Import refactored script functions
from scripts.fill_missing_bangumi import fill_missing_bangumi_links
from scripts.fill_missing_character_fields import fill_missing_character_fields
from scripts.auto_tag_completer import complete_missing_tags
from scripts.update_brand_latestBeat import update_brand_and_game_stats
from scripts.replace_and_clean_tags import run_replace_and_clean_tags
from scripts.extract_brands import export_brand_names
from scripts.export_all_tags import export_all_tags


# --- Dialog Classes (unchanged) ---

class NameSplitterDialog(QDialog):
    def __init__(self, text, parts, parent=None):
        super().__init__(parent)
        self.setWindowTitle("高风险名称分割确认")
        self.setMinimumWidth(500)
        self.result = {"action": "keep", "save_exception": False} # Default

        layout = QVBoxLayout(self)
        info_group = QGroupBox("检测到可能不正确的名称分割")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(QLabel(f"<b>原始名称:</b> {text}"))
        info_layout.addWidget(QLabel(f"<b>初步分割为:</b> {parts}"))
        info_layout.addWidget(QLabel("原因: 分割后存在过短的部分，可能是误分割。\n请选择如何处理："))
        layout.addWidget(info_group)

        self.save_exception_checkbox = QCheckBox("将原始名称加入例外列表，今后不再提示")
        self.save_exception_checkbox.setChecked(True)
        layout.addWidget(self.save_exception_checkbox)

        button_box = QDialogButtonBox()
        keep_button = button_box.addButton("保持原始名称不分割", QDialogButtonBox.AcceptRole)
        split_button = button_box.addButton("确认当前分割", QDialogButtonBox.ActionRole) 
        
        keep_button.clicked.connect(self.keep_original)
        split_button.clicked.connect(self.confirm_split)
        layout.addWidget(button_box)

    def keep_original(self):
        self.result["action"] = "keep"
        self.result["save_exception"] = self.save_exception_checkbox.isChecked()
        self.accept()

    def confirm_split(self):
        self.result["action"] = "split"
        self.result["save_exception"] = False # Splitting correctly means it's not an exception
        self.accept()

class TagTranslationDialog(QDialog):
    def __init__(self, tag, source_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("发现新标签")
        self.setMinimumWidth(400)
        self.result = "s"  # Default to skip

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"发现新的<b>【{source_name}】</b>标签: <b>{tag}</b>"))
        layout.addWidget(QLabel("请输入它的中文翻译:"))

        self.translation_input = QLineEdit()
        layout.addWidget(self.translation_input)

        button_box = QDialogButtonBox()
        ok_button = button_box.addButton("确认翻译", QDialogButtonBox.AcceptRole)
        skip_button = button_box.addButton("本次跳过", QDialogButtonBox.ActionRole)
        ignore_perm_button = button_box.addButton("永久忽略", QDialogButtonBox.ActionRole)
        cancel_button = button_box.addButton("取消操作", QDialogButtonBox.RejectRole)

        ok_button.clicked.connect(self.accept_translation)
        skip_button.clicked.connect(lambda: self.set_result_and_accept("s"))
        ignore_perm_button.clicked.connect(lambda: self.set_result_and_accept("p"))
        cancel_button.clicked.connect(self.reject)
        
        layout.addWidget(button_box)

    def accept_translation(self):
        translation = self.translation_input.text().strip()
        if not translation:
            QMessageBox.warning(self, "输入为空", "翻译内容不能为空。\n")
            return
        self.result = translation
        self.accept()

    def set_result_and_accept(self, result):
        self.result = result
        self.accept()

class BangumiSelectionDialog(QDialog):
    def __init__(self, candidates, parent=None):
        super().__init__(parent)
        self.setWindowTitle("手动选择Bangumi条目")
        self.setMinimumWidth(700)
        self.selected_id = None

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        for candidate in candidates:
            item = QListWidgetItem(candidate['display'])
            item.setData(Qt.UserRole, candidate['id'])
            self.list_widget.addItem(item)
        
        # Add a "skip" option
        skip_item = QListWidgetItem("0. 放弃匹配")
        skip_item.setData(Qt.UserRole, None) # Represent skipping with None
        self.list_widget.addItem(skip_item)

        self.list_widget.setCurrentRow(0)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        selected_item = self.list_widget.currentItem()
        if selected_item:
            self.selected_id = selected_item.data(Qt.UserRole)
        super().accept()

class BangumiMappingDialog(QDialog):
    def __init__(self, request_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("❓ Bangumi 新属性映射")
        self.setMinimumWidth(800)
        self.result = {"action": "ignore_session"} # Default action

        self.bangumi_key = request_data["bangumi_key"]
        self.bangumi_value = str(request_data["bangumi_value"])
        self.bangumi_url = request_data["bangumi_url"]
        self.db_name = request_data["db_name"]
        self.mappable_props = request_data["mappable_props"]
        self.recommended_props = request_data.get("recommended_props", [])

        main_layout = QVBoxLayout(self)

        # Info section
        info_group = QGroupBox(f"在【{self.db_name}】中发现来自 Bangumi 的新属性")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(QLabel(f"<b>键 (Key):</b> {self.bangumi_key}"))
        value_label = QLabel(f"<b>值 (Value):</b> {self.bangumi_value}")
        value_label.setWordWrap(True)
        info_layout.addWidget(value_label)
        url_label = QLabel(f'<a href="{self.bangumi_url}">在 Bangumi 上查看来源</a>')
        url_label.setOpenExternalLinks(True)
        info_layout.addWidget(url_label)
        main_layout.addWidget(info_group)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # Mapping to existing property
        mapping_group = QGroupBox("映射到现有 Notion 属性")
        mapping_layout = QVBoxLayout(mapping_group)
        self.prop_list = QListWidget()
        
        # Populate list with recommendations first
        other_props = [p for p in self.mappable_props if p not in self.recommended_props]
        
        for prop in self.recommended_props:
            item = QListWidgetItem(f"[推荐] {prop}")
            item.setData(Qt.UserRole, prop) # Store original name
            self.prop_list.addItem(item)

        if self.recommended_props and other_props:
            separator = QListWidgetItem("------ 其他所有属性 ------")
            separator.setFlags(separator.flags() & ~Qt.ItemIsSelectable)
            self.prop_list.addItem(separator)

        for prop in other_props:
            item = QListWidgetItem(prop)
            item.setData(Qt.UserRole, prop)
            self.prop_list.addItem(item)

        self.prop_list.itemDoubleClicked.connect(self.map_to_selected)
        mapping_layout.addWidget(self.prop_list)
        map_button = QPushButton("映射到选中属性")
        map_button.clicked.connect(self.map_to_selected)
        mapping_layout.addWidget(map_button)
        splitter.addWidget(mapping_group)

        # Other actions
        actions_group = QGroupBox("或执行其他操作")
        actions_layout = QVBoxLayout(actions_group)
        
        self.create_same_name_button = QPushButton(f"创建同名新属性 \'{self.bangumi_key}\'")
        self.create_custom_name_button = QPushButton("自定义新属性名称并创建")
        self.ignore_session_button = QPushButton("本次运行中忽略此属性")
        self.ignore_permanent_button = QPushButton("永久忽略此属性")
        
        self.create_same_name_button.clicked.connect(self.create_same_name)
        self.create_custom_name_button.clicked.connect(self.create_custom_name)
        self.ignore_session_button.clicked.connect(self.ignore_session)
        self.ignore_permanent_button.clicked.connect(self.ignore_permanent)

        actions_layout.addWidget(self.create_same_name_button)
        actions_layout.addWidget(self.create_custom_name_button)
        actions_layout.addStretch()
        actions_layout.addWidget(self.ignore_session_button)
        actions_layout.addWidget(self.ignore_permanent_button)
        splitter.addWidget(actions_group)

        main_layout.addWidget(splitter)

    def map_to_selected(self):
        selected_item = self.prop_list.currentItem()
        if not selected_item or not selected_item.flags() & Qt.ItemIsSelectable:
            QMessageBox.warning(self, "未选择或无效选择", "请从列表中选择一个有效的属性。\n")
            return
        
        # Retrieve the original property name from item data
        prop_name = selected_item.data(Qt.UserRole)
        self.result = {"action": "map", "data": prop_name}
        self.accept()

    def create_same_name(self):
        self.result = {"action": "create_same_name"}
        self.accept()

    def create_custom_name(self):
        custom_name, ok = QInputDialog.getText(self, "自定义属性名", "请输入要在 Notion 中创建的属性名:")
        if ok and custom_name:
            self.result = {"action": "create_custom_name", "data": custom_name}
            self.accept()

    def ignore_session(self):
        self.result = {"action": "ignore_session"}
        self.accept()

    def ignore_permanent(self):
        reply = QMessageBox.question(self, "永久忽略", f"确定要将 \'{self.bangumi_key}\' 加入永久忽略列表吗？\n此操作会修改 mapping/bangumi_ignore_list.json 文件。",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.result = {"action": "ignore_permanent"}
            self.accept()

class PropertyTypeDialog(QDialog):
    def __init__(self, prop_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择新属性类型")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"请为新属性 \'{prop_name}\' 选择一个 Notion 类型："))
        self.combo = QComboBox()
        # Using the imported TYPE_SELECTION_MAP
        for key, (api_type, display_name) in TYPE_SELECTION_MAP.items():
            self.combo.addItem(f"{display_name} ({api_type})", api_type)
        layout.addWidget(self.combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_type(self):
        return self.combo.currentData()


class SelectionDialog(QDialog):

    SEARCH_FANZA_ROLE = QDialogButtonBox.ActionRole
    def __init__(self, items, title="请选择", source="dlsite", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(700)
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        for item_text in items:
            self.list_widget.addItem(item_text)
        self.list_widget.setCurrentRow(0)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if source == "dlsite":
            self.fanza_button = self.buttons.addButton("换用Fanza搜索", self.SEARCH_FANZA_ROLE)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.clicked.connect(self.handle_button_click)
        layout.addWidget(self.buttons)
    def handle_button_click(self, button):
        role = self.buttons.buttonRole(button)
        if role == self.SEARCH_FANZA_ROLE:
            self.done(2)
    def selected_index(self):
        return self.list_widget.currentRow()

class DuplicateConfirmationDialog(QDialog):
    def __init__(self, candidates, parent=None):
        super().__init__(parent)
        self.setWindowTitle("检测到可能重复的游戏")
        self.setMinimumWidth(600)
        self.result = "skip"
        layout = QVBoxLayout(self)
        label = QLabel("在Notion中发现以下相似条目：")
        layout.addWidget(label)
        list_widget = QListWidget()
        for item, score in candidates:
            list_widget.addItem(f"{item.get('title')} (相似度: {score:.2f})")
        layout.addWidget(list_widget)
        button_box = QDialogButtonBox()
        update_button = button_box.addButton("更新最相似游戏", QDialogButtonBox.ActionRole)
        create_button = button_box.addButton("强制创建新游戏", QDialogButtonBox.ActionRole)
        skip_button = button_box.addButton("跳过此游戏", QDialogButtonBox.RejectRole)
        update_button.clicked.connect(lambda: self.set_result_and_accept("update"))
        create_button.clicked.connect(lambda: self.set_result_and_accept("create"))
        skip_button.clicked.connect(lambda: self.set_result_and_accept("skip"))
        layout.addWidget(button_box)
    def set_result_and_accept(self, result):
        self.result = result
        self.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Otaku Sync - 图形工具")
        
        screen = QApplication.primaryScreen()
        available_geometry = screen.availableGeometry()
        self.resize(int(available_geometry.width() * 0.7), int(available_geometry.height() * 0.8))
        self.move(available_geometry.center() - self.rect().center())

        self.game_sync_worker = None
        self.script_worker = None
        self.shared_context = None
        self.current_mapping_file = None
        self.current_data = {}
        self.script_buttons = []

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # Top search layout
        top_layout = QHBoxLayout()
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("输入游戏名/关键词...")
        self.manual_mode_checkbox = QCheckBox("手动模式")
        self.search_button = QPushButton("🔍 开始搜索")
        self.search_button.setStyleSheet("background-color: #007BFF; color: white; padding: 5px;")
        top_layout.addWidget(QLabel("游戏名:"))
        top_layout.addWidget(self.keyword_input, 1)
        top_layout.addWidget(self.manual_mode_checkbox)
        top_layout.addWidget(self.search_button)
        main_layout.addLayout(top_layout)

        # Main splitter for controls and log
        main_splitter = QSplitter(Qt.Vertical)

        # Top widget with all controls
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(self.create_batch_tools_group())
        controls_layout.addWidget(self.create_mapping_editor())
        
        # Bottom widget for the log console
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.addWidget(QLabel("运行日志"))
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        log_layout.addWidget(self.log_console)

        main_splitter.addWidget(controls_widget)
        main_splitter.addWidget(log_widget)

        # Adjust splitter sizes (e.g., 70% for controls, 30% for log)
        main_splitter.setSizes([int(self.height() * 0.7), int(self.height() * 0.3)])
        main_layout.addWidget(main_splitter)
        
        patch_logger()
        log_bridge.log_received.connect(self.log_console.appendPlainText)
        
        self.init_shared_context() # Initialize context at startup

        project_logger.success("✅ 初始化完成，可以开始使用。\n")

        self.search_button.clicked.connect(self.start_search_process)
        self.keyword_input.returnPressed.connect(self.start_search_process)

    def init_shared_context(self):
        """Initializes the shared context for the application."""
        project_logger.system("🔧 正在初始化应用程序级共享上下文...")
        self.shared_context = create_shared_context()
        project_logger.system("✅ 应用程序级共享上下文已准备就绪。\n")

    def changeEvent(self, event):
        """捕获窗口状态变更，例如当窗口获得焦点时。"""
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.keyword_input.setFocus()
            self.keyword_input.selectAll()

    def create_batch_tools_group(self):
        batch_tools_group = QGroupBox("批处理工具")
        layout = QHBoxLayout(batch_tools_group)

        buttons_to_create = [
            ("补全Bangumi链接", fill_missing_bangumi_links),
            ("补全角色字段", fill_missing_character_fields),
            ("补全游戏标签", complete_missing_tags),
            ("更新厂商统计", update_brand_and_game_stats),
            ("清理与替换标签", run_replace_and_clean_tags),
            ("导出所有品牌名", export_brand_names),
            ("导出所有标签", export_all_tags),
        ]

        self.script_buttons = []
        for (name, func) in buttons_to_create:
            button = QPushButton(name)
            button.clicked.connect(partial(self.start_script_execution, func, name))
            layout.addWidget(button)
            self.script_buttons.append(button)
        
        layout.addStretch()
        return batch_tools_group

    def create_mapping_editor(self):
        editor_container = QGroupBox("映射文件编辑器")
        main_layout = QVBoxLayout(editor_container)
        top_controls = QHBoxLayout()
        top_controls.addWidget(QLabel("映射文件:"))
        self.mapping_files_combo = QComboBox()
        top_controls.addWidget(self.mapping_files_combo, 1)
        self.save_button = QPushButton("💾 保存更改")
        top_controls.addWidget(self.save_button)
        main_layout.addLayout(top_controls)
        
        editor_splitter = QSplitter(Qt.Horizontal)
        master_widget = QWidget()
        master_layout = QVBoxLayout(master_widget)
        master_layout.addWidget(QLabel("原始值 (Keys)"))
        self.master_list = QListWidget()
        master_layout.addWidget(self.master_list)
        master_buttons = QHBoxLayout()
        self.add_key_button = QPushButton("➕")
        self.delete_key_button = QPushButton("➖")
        master_buttons.addStretch()
        master_buttons.addWidget(self.add_key_button)
        master_buttons.addWidget(self.delete_key_button)
        master_layout.addLayout(master_buttons)
        
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.addWidget(QLabel("映射值 (Values) - 双击修改"))
        self.detail_list = QListWidget()
        self.detail_list.setAlternatingRowColors(True)
        detail_layout.addWidget(self.detail_list)
        detail_buttons = QHBoxLayout()
        self.add_value_button = QPushButton("➕")
        self.delete_value_button = QPushButton("➖")
        detail_buttons.addStretch()
        detail_buttons.addWidget(self.add_value_button)
        detail_buttons.addWidget(self.delete_value_button)
        detail_layout.addLayout(detail_buttons)
        
        editor_splitter.addWidget(master_widget)
        editor_splitter.addWidget(detail_widget)
        editor_splitter.setSizes([300, 600])
        main_layout.addWidget(editor_splitter)

        self.mapping_files_combo.currentTextChanged.connect(self.load_selected_file)
        self.master_list.currentItemChanged.connect(self.display_details)
        self.detail_list.itemDoubleClicked.connect(self.edit_detail_item)
        self.save_button.clicked.connect(self.save_current_file)
        self.add_key_button.clicked.connect(self.add_key)
        self.delete_key_button.clicked.connect(self.delete_key)
        self.add_value_button.clicked.connect(self.add_value)
        self.delete_value_button.clicked.connect(self.delete_value)
        self.populate_mapping_files()
        return editor_container

    def set_shared_context(self, context):
        if not self.shared_context:
            project_logger.system("主窗口已接收并保存共享的应用上下文。\n")
            self.shared_context = context

    def start_search_process(self):
        if self.game_sync_worker and self.game_sync_worker.isRunning() or self.script_worker and self.script_worker.isRunning():
            QMessageBox.warning(self, "任务正在进行", "请等待当前任务完成。\n")
            return
        keyword = self.keyword_input.text().strip()
        if not keyword:
            project_logger.warn("请输入游戏名/关键词后再开始搜索。\n")
            return
        self.search_button.setEnabled(False)
        self.search_button.setText("正在运行...")
        self.log_console.clear()
        manual_mode = self.manual_mode_checkbox.isChecked()
        
        self.game_sync_worker = GameSyncWorker(keyword=keyword, manual_mode=manual_mode, shared_context=self.shared_context, parent=self)
        self.game_sync_worker.context_created.connect(self.set_shared_context)
        self.game_sync_worker.selection_required.connect(self.handle_selection_required)
        self.game_sync_worker.duplicate_check_required.connect(self.handle_duplicate_check)
        self.game_sync_worker.bangumi_mapping_required.connect(self.handle_bangumi_mapping)
        self.game_sync_worker.property_type_required.connect(self.handle_property_type)
        self.game_sync_worker.bangumi_selection_required.connect(self.handle_bangumi_selection_required)
        self.game_sync_worker.tag_translation_required.connect(self.handle_tag_translation_required)
        self.game_sync_worker.concept_merge_required.connect(self.handle_concept_merge_required)
        self.game_sync_worker.name_split_decision_required.connect(self.handle_name_split_decision_required)
        self.game_sync_worker.process_completed.connect(self.process_finished)
        self.game_sync_worker.finished.connect(self.cleanup_worker)
        self.game_sync_worker.start()

    def start_script_execution(self, script_func, script_name):
        if self.game_sync_worker and self.game_sync_worker.isRunning() or self.script_worker and self.script_worker.isRunning():
            QMessageBox.warning(self, "任务正在进行", "请等待当前任务完成。\n")
            return
        
        project_logger.system(f"即将执行脚本: {script_name}")
        self.log_console.clear()
        self.set_all_buttons_enabled(False)

        self.script_worker = ScriptWorker(script_func, script_name, shared_context=self.shared_context, parent=self)
        self.script_worker.context_created.connect(self.set_shared_context)
        self.script_worker.script_completed.connect(self.on_script_completed)
        self.script_worker.finished.connect(self.cleanup_worker)
        self.script_worker.start()

    def on_script_completed(self, script_name, success):
        project_logger.info(f'脚本 "{script_name}" 执行结束，结果: {"成功" if success else "失败"}\n')
        self.set_all_buttons_enabled(True)

    def set_all_buttons_enabled(self, enabled):
        self.search_button.setEnabled(enabled)
        for button in self.script_buttons:
            button.setEnabled(enabled)

    def handle_name_split_decision_required(self, text, parts):
        project_logger.info(f"需要为名称 '{text}' 的分割方式 '{parts}' 做出决策...")
        dialog = NameSplitterDialog(text, parts, self)
        worker = self.sender()
        if dialog.exec() == QDialog.Accepted:
            worker.set_interaction_response(dialog.result)
        else:
            worker.set_interaction_response({"action": "keep", "save_exception": False})

    def handle_tag_translation_required(self, tag, source_name):
        project_logger.info(f"需要为新标签 \'{tag}\' ({source_name}) 提供翻译...")
        dialog = TagTranslationDialog(tag, source_name, self)
        worker = self.sender()
        if dialog.exec() == QDialog.Accepted:
            worker.set_interaction_response(dialog.result)
        else:
            worker.set_interaction_response("s") # Treat cancel as skip

    def handle_concept_merge_required(self, concept, candidate):
        project_logger.info(f"需要为新概念 \'{concept}\' 选择合并策略...")
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("概念合并")
        msg_box.setText(f"新标签概念 '<b>{concept}</b>' 与现有标签 '<b>{candidate}</b>' 高度相似。")
        msg_box.setInformativeText("是否要将新概念合并到现有标签中？")
        merge_button = msg_box.addButton("合并 (推荐)", QMessageBox.AcceptRole)
        create_button = msg_box.addButton("创建为新标签", QMessageBox.ActionRole)
        msg_box.addButton("取消", QMessageBox.RejectRole)
        
        msg_box.exec()
        worker = self.sender()

        if msg_box.clickedButton() == merge_button:
            worker.set_interaction_response("merge")
        elif msg_box.clickedButton() == create_button:
            worker.set_interaction_response("create")
        else:
            worker.set_interaction_response(None) # Cancel

    def handle_bangumi_selection_required(self, candidates):
        project_logger.system("[GUI] Received bangumi_selection_required, creating dialog.")
        dialog = BangumiSelectionDialog(candidates, self)
        worker = self.sender()
        if dialog.exec() == QDialog.Accepted:
            worker.set_interaction_response(dialog.selected_id)
        else:
            worker.set_interaction_response(None) # User cancelled

    def handle_bangumi_mapping(self, request_data):
        project_logger.info("需要进行 Bangumi 属性映射，等待用户操作...\n")
        dialog = BangumiMappingDialog(request_data, self)
        dialog.exec()
        self.sender().set_interaction_response(dialog.result)

    def handle_property_type(self, request_data):
        project_logger.info(f"需要为新属性 \'{request_data['prop_name']}\' 选择类型...\n")
        dialog = PropertyTypeDialog(request_data['prop_name'], self)
        worker = self.sender()
        if dialog.exec() == QDialog.Accepted:
            selected_type = dialog.selected_type()
            worker.set_interaction_response(selected_type)
        else:
            worker.set_interaction_response(None)

    def handle_selection_required(self, choices, title, source):
        if not choices:
            project_logger.warn("未找到任何结果。\n")
            self.game_sync_worker.set_choice(None)
            return
        project_logger.info(f"接收到 {len(choices)} 个选项，请在弹出对话框中选择...\n")
        display_items = []
        if source == 'ggbases':
            for item in choices:
                size_info = item.get('容量', '未知')
                popularity = item.get('popularity', 0)
                display_items.append(f"{item.get('title', 'No Title')} (热度: {popularity}) (大小: {size_info})")
        else:
            for item in choices:
                price = item.get("价格") or item.get("price", "未知")
                price_display = f"{price}円" if str(price).isdigit() else price
                item_type = item.get("类型", "未知")
                display_items.append(f"[{source.upper()}] {item.get('title', 'No Title')} | 💴 {price_display} | 🏷️ {item_type}")
        dialog = SelectionDialog(display_items, title=title, source=source, parent=self)
        result = dialog.exec() 
        if result == QDialog.Accepted:
            choice_index = dialog.selected_index()
            project_logger.info(f"用户选择了第 {choice_index + 1} 项。\n")
            self.game_sync_worker.set_choice(choice_index)
        elif result == 2:
            project_logger.info("用户选择切换到 Fanza 搜索...\n")
            self.game_sync_worker.set_choice("search_fanza")
        else:
            project_logger.info("用户取消了选择。\n")
            self.game_sync_worker.set_choice(-1)

    def handle_duplicate_check(self, candidates):
        project_logger.info("发现可能重复的游戏，等待用户确认...\n")
        dialog = DuplicateConfirmationDialog(candidates, self)
        dialog.exec()
        choice = dialog.result
        project_logger.info(f"用户对重复游戏的操作是: {choice}\n")
        self.game_sync_worker.set_choice(choice)

    def process_finished(self, success):
        project_logger.info(f"任务完成，结果: {"成功" if success else "失败"}\n")
        self.set_all_buttons_enabled(True)

    def cleanup_worker(self):
        project_logger.info("后台线程已退出，正在清理...\n")
        sender = self.sender()
        if sender == self.game_sync_worker:
            self.game_sync_worker.deleteLater()
            self.game_sync_worker = None
        elif sender == self.script_worker:
            self.script_worker.deleteLater()
            self.script_worker = None

    def closeEvent(self, event):
        if (self.game_sync_worker and self.game_sync_worker.isRunning()) or \
           (self.script_worker and self.script_worker.isRunning()):
            reply = QMessageBox.question(self, '任务正在进行', 
                                       "当前有任务正在后台运行，强制退出可能导致数据不一致或浏览器进程残留。\n\n确定要退出吗？",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                project_logger.warn("用户选择强制退出。\n")
            else:
                event.ignore()
                return
        
        project_logger.system("正在清理应用资源并保存所有数据...")
        # Use the unified shutdown function
        if self.shared_context:
            # Running an async function from a sync event handler
            # is tricky. A simple way is to run it in a new event loop.
            try:
                # The loop specific context (like http client) is not available here,
                # but close_context is designed to handle that.
                asyncio.run(close_context(self.shared_context))
            except Exception as e:
                project_logger.error(f"关闭应用时发生错误: {e}")

        project_logger.system("程序已安全退出。\n")
        event.accept()

    def populate_mapping_files(self):
        self.mapping_dir = os.path.join(os.path.dirname(__file__), 'mapping')
        NON_EDITABLE_FILES = ['tag_ignore_list.json', 'bangumi_ignore_list.json', 'name_split_exceptions.json']
        try:
            files = [f for f in os.listdir(self.mapping_dir) if f.endswith('.json') and f not in NON_EDITABLE_FILES]
            self.mapping_files_combo.addItems(files)
            if files:
                self.load_selected_file(files[0])
        except FileNotFoundError:
            log_bridge.log_received.emit(f"❌ 错误：未找到 'mapping' 文件夹。\n")
            self.save_button.setEnabled(False)

    def set_editor_enabled(self, enabled):
        self.save_button.setEnabled(enabled)
        self.add_key_button.setEnabled(enabled)
        self.delete_key_button.setEnabled(enabled)
        self.add_value_button.setEnabled(enabled)
        self.delete_value_button.setEnabled(enabled)
        self.detail_list.setEnabled(enabled)
        self.master_list.setEnabled(enabled)

    def flatten_dict(self, d, parent_key='', sep='.'):
        items = []
        for k, v in d.items():
            new_key = parent_key + sep + k if parent_key else k
            if isinstance(v, dict):
                items.extend(self.flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    def unflatten_dict(self, d, sep='.'):
        result = {}
        for key, value in d.items():
            parts = key.split(sep)
            d = result
            for part in parts[:-1]:
                if part not in d:
                    d[part] = {}
                d = d[part]
            d[parts[-1]] = value
        return result

    def load_selected_file(self, filename=None):
        if filename is None:
            filename = self.mapping_files_combo.currentText()
        if not filename:
            return
        self.current_mapping_file = os.path.join(self.mapping_dir, filename)
        try:
            with open(self.current_mapping_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            log_bridge.log_received.emit(f"❌ 加载文件 \'{filename}\'失败: {e}\n")
            data = {}
        
        self.master_list.clear()
        self.detail_list.clear()

        if isinstance(data, dict):
            self.current_data = self.flatten_dict(data)
            self.set_editor_enabled(True)
            sorted_keys = sorted(self.current_data.keys())
            self.master_list.addItems(sorted_keys)
            if sorted_keys:
                self.master_list.setCurrentRow(0)
        elif isinstance(data, list):
            log_bridge.log_received.emit(f"⚠️ 文件 \'{os.path.basename(self.current_mapping_file)}\' 是一个列表，当前编辑器不支持直接编辑。\n")
            self.set_editor_enabled(False)
            self.detail_list.addItems([str(item) for item in data])
        else:
            self.set_editor_enabled(False)
            log_bridge.log_received.emit(f"❌ 不支持的数据格式: {type(data)}\n")

    def display_details(self, current_item, _=None):
        self.detail_list.clear()
        if not current_item:
            return
        key = current_item.text()
        values = self.current_data.get(key, [])
        
        # Ensure values are always treated as a list for display
        if not isinstance(values, list):
            values = [values]
            
        self.detail_list.addItems([str(v) for v in values])

    def edit_detail_item(self, item):
        key_item = self.master_list.currentItem()
        if not key_item: return
        key = key_item.text()
        
        old_value = item.text()
        row = self.detail_list.row(item)

        new_value, ok = QInputDialog.getText(self, "修改映射值", "新值:", QLineEdit.Normal, old_value)

        if ok and new_value != old_value:
            current_values = self.current_data.get(key)
            if isinstance(current_values, list):
                current_values[row] = new_value
            else: # It's a single value (str, int, etc.)
                self.current_data[key] = new_value
            
            # Refresh the view for the edited item
            self.display_details(key_item)
            # Reselect the edited item
            self.detail_list.setCurrentRow(row)
            log_bridge.log_received.emit(f"🔧 值已在界面中更新，请记得保存。\n")

    def save_current_file(self):
        if not self.current_mapping_file:
            QMessageBox.warning(self, "没有文件", "没有选择要保存的文件。\n")
            return
        
        try:
            # Unflatten the data before saving
            unflattened_data = self.unflatten_dict(self.current_data)
            with open(self.current_mapping_file, 'w', encoding='utf-8') as f:
                json.dump(unflattened_data, f, indent=4, ensure_ascii=False)
            log_bridge.log_received.emit(f"✅ 文件 \'{os.path.basename(self.current_mapping_file)}\' 已成功保存。\n")
            # Reload to reflect the correct structure if there were any structural changes
            self.load_selected_file()
        except Exception as e:
            log_bridge.log_received.emit(f"❌ 保存文件失败: {e}\n")
            QMessageBox.critical(self, "保存失败", f"无法保存文件: {e}\n")

    def add_key(self):
        key, ok = QInputDialog.getText(self, "添加新键", "输入新的原始值 (Key), 可用 '.' 来创建层级:")
        if ok and key:
            if key in self.current_data:
                QMessageBox.warning(self, "键已存在", f"键 \'{key}\' 已存在。\n")
                return
            self.current_data[key] = [] 
            self.master_list.addItem(key)
            self.master_list.sortItems()
            # Find and select the newly added item
            items = self.master_list.findItems(key, Qt.MatchExactly)
            if items:
                self.master_list.setCurrentItem(items[0])
            log_bridge.log_received.emit(f"🔧 已添加新键 \'{key}\'，请为其添加值并保存。\n")

    def delete_key(self):
        current_item = self.master_list.currentItem()
        if not current_item: return
        
        key = current_item.text()
        reply = QMessageBox.question(self, "确认删除", f"确定要删除键 \'{key}\' 及其所有映射值吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Remove from master list
            row = self.master_list.row(current_item)
            self.master_list.takeItem(row)
            
            # Delete from data
            if key in self.current_data:
                del self.current_data[key]
                
            self.detail_list.clear()
            log_bridge.log_received.emit(f"🔧 已删除键 \'{key}\'，请记得保存。\n")

    def add_value(self):
        current_key_item = self.master_list.currentItem()
        if not current_key_item:
            QMessageBox.warning(self, "没有选择键", "请先在左侧选择一个键。\n")
            return
        key = current_key_item.text()

        value, ok = QInputDialog.getText(self, "添加新值", f"为 \'{key}\' 添加新的映射值:")
        if ok and value:
            current_values = self.current_data.get(key)
            
            if not isinstance(current_values, list): # If it's not a list, make it one
                if current_values is not None and str(current_values).strip() != "":
                    current_values = [current_values]
                else:
                    current_values = []

            if value in [str(v) for v in current_values]:
                QMessageBox.warning(self, "值已存在", f"值 \'{value}\' 已经存在于 \'{key}\' 的映射中。\n")
                return
            
            current_values.append(value)
            self.current_data[key] = current_values
            self.display_details(current_key_item) # Refresh details
            log_bridge.log_received.emit(f"🔧 已为 \'{key}\' 添加值 \'{value}\'，请记得保存。\n")

    def delete_value(self):
        current_key_item = self.master_list.currentItem()
        current_value_item = self.detail_list.currentItem()
        if not current_key_item or not current_value_item: return
        
        key = current_key_item.text()
        value_to_delete = current_value_item.text()
        
        current_values = self.current_data.get(key)
        
        if isinstance(current_values, list):
            reply = QMessageBox.question(self, "确认删除", f"确定要从 \'{key}\' 中删除值 \'{value_to_delete}\' 吗？",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                # Find the value to remove, converting to string for comparison
                try:
                    # Find the index of the value to delete
                    index_to_del = -1
                    for i, v in enumerate(current_values):
                        if str(v) == value_to_delete:
                            index_to_del = i
                            break
                    
                    if index_to_del != -1:
                        current_values.pop(index_to_del)
                        self.current_data[key] = current_values
                        self.display_details(current_key_item) # Refresh
                        log_bridge.log_received.emit(f"🔧 已删除值 \'{value_to_delete}\'，请记得保存。\n")

                except ValueError:
                    pass # Should not happen
        else: # Single value
             reply = QMessageBox.question(self, "确认删除", f"确定要删除 \'{key}\' 的值 \'{value_to_delete}\' 吗？ (这会清空该键的值)",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
             if reply == QMessageBox.Yes:
                self.current_data[key] = "" # Set to empty string
                self.display_details(current_key_item)
                log_bridge.log_received.emit(f"🔧 已清空键 \'{key}\' 的值，请记得保存。\n")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
