
import asyncio
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QComboBox, QListWidget, QListWidgetItem, QPushButton, QLabel, QMessageBox, 
    QInputDialog, QLineEdit, QPlainTextEdit, QDialog, QDialogButtonBox, QCheckBox,
    QGroupBox, QGridLayout
)
from PySide6.QtCore import Qt
from core.interaction import TYPE_SELECTION_MAP

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
    def __init__(self, game_name, candidates, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"为【{game_name}】选择Bangumi条目")
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
        
        self.create_same_name_button = QPushButton(f"创建同名新属性 '{self.bangumi_key}'")
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
        reply = QMessageBox.question(self, "永久忽略", f"确定要将 '{self.bangumi_key}' 加入永久忽略列表吗？\n此操作会修改 mapping/bangumi_ignore_list.json 文件。",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.result = {"action": "ignore_permanent"}
            self.accept()

class PropertyTypeDialog(QDialog):
    def __init__(self, prop_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择新属性类型")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"请为新属性 '{prop_name}' 选择一个 Notion 类型："))
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
