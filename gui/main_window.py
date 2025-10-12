
import sys
import asyncio
import threading
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QMessageBox, QLineEdit, QPlainTextEdit, QDialog, QCheckBox
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QScreen

from utils.gui_bridge import patch_logger, log_bridge
from core.gui_worker import GameSyncWorker, ScriptWorker
from utils import logger as project_logger
from core.context_factory import create_shared_context
from core.init import close_context
from core.cache_warmer import warm_up_brand_cache_standalone

# Import dialogs and widgets from the new GUI package
from .dialogs import (
    NameSplitterDialog, TagTranslationDialog, BangumiSelectionDialog, 
    BangumiMappingDialog, PropertyTypeDialog, SelectionDialog, 
    DuplicateConfirmationDialog
)
from .widgets import BatchToolsWidget, MappingEditorWidget


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

        # Top widget with all controls - now composed of smaller widgets
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        
        self.batch_tools_widget = BatchToolsWidget()
        self.mapping_editor_widget = MappingEditorWidget()

        controls_layout.addWidget(self.batch_tools_widget)
        controls_layout.addWidget(self.mapping_editor_widget)
        
        # Bottom widget for the log console
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.addWidget(QLabel("运行日志"))
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        log_layout.addWidget(self.log_console)

        main_splitter.addWidget(controls_widget)
        main_splitter.addWidget(log_widget)

        main_splitter.setSizes([int(self.height() * 0.7), int(self.height() * 0.3)])
        main_layout.addWidget(main_splitter)
        
        # Setup logging
        patch_logger()
        log_bridge.log_received.connect(self.log_console.appendPlainText)
        # Connect the mapping editor's log signal
        self.mapping_editor_widget.log_message.connect(self.log_console.appendPlainText)
        
        self.init_shared_context()
        self.run_background_tasks()

        project_logger.success("✅ 初始化完成，可以开始使用.\n")

        # Connect signals
        self.search_button.clicked.connect(self.start_search_process)
        self.keyword_input.returnPressed.connect(self.start_search_process)
        self.batch_tools_widget.script_triggered.connect(self.start_script_execution)

    def init_shared_context(self):
        project_logger.system("🔧 正在初始化应用程序级共享上下文...")
        self.shared_context = create_shared_context()

        # 程序启动时，在后台预创建所需的浏览器驱动
        if self.shared_context.get("driver_factory"):
            project_logger.system("🚀 在后台预启动浏览器驱动...")
            driver_factory = self.shared_context["driver_factory"]
            driver_factory.start_background_creation(["dlsite_driver", "ggbases_driver"])

        project_logger.system("✅ 应用程序级共享上下文已准备就绪.\n")

    def run_background_tasks(self):
        # Wrapper to run asyncio code in a separate thread
        def run_async_task(task):
            try:
                asyncio.run(task)
            except Exception as e:
                # Log errors to the main log file, but don't interact with GUI
                project_logger.error(f"后台任务执行失败: {e}", exc_info=True)

        # Start brand cache warming in a daemon thread
        cache_thread = threading.Thread(target=run_async_task, args=(warm_up_brand_cache_standalone(),))
        cache_thread.daemon = True
        cache_thread.start()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.keyword_input.setFocus()
            self.keyword_input.selectAll()

    def set_shared_context(self, context):
        if not self.shared_context:
            project_logger.system("主窗口已接收并保存共享的应用上下文.\n")
            self.shared_context = context

    def start_search_process(self):
        if self.is_worker_running():
            return
        keyword = self.keyword_input.text().strip()
        if not keyword:
            project_logger.warn("请输入游戏名/关键词后再开始搜索.\n")
            return
        
        self.set_all_buttons_enabled(False)
        self.search_button.setText("正在运行...")
        self.log_console.clear()
        manual_mode = self.manual_mode_checkbox.isChecked()
        
        self.game_sync_worker = GameSyncWorker(keyword=keyword, manual_mode=manual_mode, shared_context=self.shared_context, parent=self)
        self.connect_worker_signals(self.game_sync_worker)
        self.game_sync_worker.start()

    def start_script_execution(self, script_func, script_name):
        if self.is_worker_running():
            return
        
        project_logger.system(f"即将执行脚本: {script_name}")
        self.log_console.clear()
        self.set_all_buttons_enabled(False)

        self.script_worker = ScriptWorker(script_func, script_name, shared_context=self.shared_context, parent=self)
        self.script_worker.context_created.connect(self.set_shared_context)
        self.script_worker.script_completed.connect(self.on_script_completed)
        self.script_worker.finished.connect(self.cleanup_worker)
        self.script_worker.start()

    def is_worker_running(self):
        if self.game_sync_worker and self.game_sync_worker.isRunning() or self.script_worker and self.script_worker.isRunning():
            QMessageBox.warning(self, "任务正在进行", "请等待当前任务完成.\n")
            return True
        return False

    def connect_worker_signals(self, worker):
        worker.context_created.connect(self.set_shared_context)
        worker.selection_required.connect(self.handle_selection_required)
        worker.duplicate_check_required.connect(self.handle_duplicate_check)
        worker.bangumi_mapping_required.connect(self.handle_bangumi_mapping)
        worker.property_type_required.connect(self.handle_property_type)
        worker.bangumi_selection_required.connect(self.handle_bangumi_selection_required)
        worker.tag_translation_required.connect(self.handle_tag_translation_required)
        worker.concept_merge_required.connect(self.handle_concept_merge_required)
        worker.name_split_decision_required.connect(self.handle_name_split_decision_required)
        worker.process_completed.connect(self.process_finished)
        worker.finished.connect(self.cleanup_worker)

    def on_script_completed(self, script_name, success):
        project_logger.info(f'脚本 "{script_name}" 执行结束，结果: {"成功" if success else "失败"}\n')
        self.set_all_buttons_enabled(True)

    def set_all_buttons_enabled(self, enabled):
        self.search_button.setEnabled(enabled)
        self.search_button.setText("🔍 开始搜索" if enabled else "正在运行...")
        self.batch_tools_widget.set_buttons_enabled(enabled)

    # --- All handler methods for dialogs --- #

    def handle_name_split_decision_required(self, text, parts):
        project_logger.info(f"需要为名称 '{text}' 的分割方式 '{parts}' 做出决策...")
        dialog = NameSplitterDialog(text, parts, self)
        worker = self.sender()
        if dialog.exec() == QDialog.Accepted:
            worker.set_interaction_response(dialog.result)
        else:
            worker.set_interaction_response({"action": "keep", "save_exception": False})

    def handle_tag_translation_required(self, tag, source_name):
        project_logger.info(f"需要为新标签 '{tag}' ({source_name}) 提供翻译...")
        dialog = TagTranslationDialog(tag, source_name, self)
        worker = self.sender()
        if dialog.exec() == QDialog.Accepted:
            worker.set_interaction_response(dialog.result)
        else:
            worker.set_interaction_response("s") # Treat cancel as skip

    def handle_concept_merge_required(self, concept, candidate):
        project_logger.info(f"需要为新概念 '{concept}' 选择合并策略...")
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

    def handle_bangumi_selection_required(self, game_name, candidates):
        project_logger.system("[GUI] Received bangumi_selection_required, creating dialog.")
        dialog = BangumiSelectionDialog(game_name, candidates, self)
        worker = self.sender()
        
        result = dialog.exec()

        if result == QDialog.Accepted:
            worker.set_interaction_response(dialog.selected_id)
        else:
            worker.set_interaction_response(None)

    def handle_bangumi_mapping(self, request_data):
        project_logger.info("需要进行 Bangumi 属性映射，等待用户操作...\n")
        dialog = BangumiMappingDialog(request_data, self)
        dialog.exec()
        self.sender().set_interaction_response(dialog.result)

    def handle_property_type(self, request_data):
        project_logger.info(f"需要为新属性 '{request_data['prop_name']}' 选择类型...\n")
        dialog = PropertyTypeDialog(request_data['prop_name'], self)
        worker = self.sender()
        if dialog.exec() == QDialog.Accepted:
            selected_type = dialog.selected_type()
            worker.set_interaction_response(selected_type)
        else:
            worker.set_interaction_response(None)

    def handle_selection_required(self, choices, title, source):
        worker = self.sender()
        if not worker:
            return

        if not choices:
            project_logger.warn("未找到任何结果.\n")
            worker.set_choice(None)
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
            worker.set_choice(choice_index)
        elif result == 2:
            project_logger.info("用户选择切换到 Fanza 搜索...\n")
            worker.set_choice("search_fanza")
        else:
            project_logger.info("用户取消了选择。\n")
            worker.set_choice(-1)

    def handle_duplicate_check(self, candidates):
        worker = self.sender()
        if not worker:
            return
            
        project_logger.info("发现可能重复的游戏，等待用户确认...\n")
        dialog = DuplicateConfirmationDialog(candidates, self)
        dialog.exec()
        choice = dialog.result
        project_logger.info(f"用户对重复游戏的操作是: {choice}\n")
        worker.set_choice(choice)

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
        if self.shared_context:
            try:
                asyncio.run(close_context(self.shared_context))
            except Exception as e:
                project_logger.error(f"关闭应用时发生错误: {e}")

        project_logger.system("程序已安全退出。\n")
        event.accept()
