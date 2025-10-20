import os
import json
from functools import partial
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QComboBox, QListWidget, QPushButton, QLabel, QMessageBox,
    QInputDialog, QLineEdit, QGroupBox, QFormLayout, QStyle,
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor, QPixmap, QPainter, QIcon, QPen

# Import the new FlowLayout
from .flow_layout import FlowLayout

# Import script functions directly
from scripts.fill_missing_bangumi import fill_missing_bangumi_links
from scripts.fill_missing_character_fields import fill_missing_character_fields
from scripts.auto_tag_completer import complete_missing_tags
from scripts.update_brand_latestBeat import update_brand_and_game_stats
from scripts.replace_and_clean_tags import run_replace_and_clean_tags
from scripts.extract_brands import export_brand_names
from scripts.export_all_tags import export_all_tags

def apply_glow_effect(widget, color="#888888", blur_radius=10, x_offset=2, y_offset=2):
    """为给定的组件应用一个辉光或阴影效果。"""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur_radius)
    shadow.setColor(QColor(color))
    shadow.setOffset(x_offset, y_offset)
    widget.setGraphicsEffect(shadow)

def create_plus_icon(color, size=QSize(14, 14)):
    """程序化绘制一个清晰的 '+' 号图标。"""
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    pen = QPen(QColor(color), 2) # 笔刷宽度为2px
    pen.setCapStyle(Qt.RoundCap) # 圆润的笔端
    painter.setPen(pen)
    painter.setRenderHint(QPainter.Antialiasing) # 抗锯齿
    
    # 绘制两条线组成 '+'
    center = size.width() / 2
    line_len = size.width() * 0.7
    start_pos = center - line_len / 2
    end_pos = center + line_len / 2
    
    painter.drawLine(start_pos, center, end_pos, center) # 水平线
    painter.drawLine(center, start_pos, center, end_pos) # 垂直线
    
    painter.end()
    return QIcon(pixmap)

class BatchToolsWidget(QGroupBox):
    """A widget group for all batch script execution buttons."""
    # Signal: script_function, script_name
    script_triggered = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__("批处理工具", parent)
        # Use the new FlowLayout
        layout = FlowLayout(self)

        buttons_to_create = [
            ("补全Bangumi链接", fill_missing_bangumi_links),
            ("补全角色字段", fill_missing_character_fields),
            ("补全游戏标签", complete_missing_tags),
            ("更新厂商统计", update_brand_and_game_stats),
            ("清理与替换标签", run_replace_and_clean_tags),
            ("导出所有品牌名", export_brand_names),
            ("导出所有标签", export_all_tags),
        ]

        self.buttons = []
        for (name, func) in buttons_to_create:
            button = QPushButton(name)
            # Use a partial to pass arguments to the slot
            button.clicked.connect(partial(self.trigger_script, func, name))
            layout.addWidget(button)
            self.buttons.append(button)

    def trigger_script(self, func, name):
        """Emits the signal to the main window to run the script."""
        self.script_triggered.emit(func, name)

    def set_buttons_enabled(self, enabled):
        """Enable or disable all buttons in this widget."""
        for button in self.buttons:
            button.setEnabled(enabled)


class MappingEditorWidget(QGroupBox):
    """A complex widget for editing mapping JSON files."""
    log_message = Signal(str)
    dirty_status_changed = Signal(bool)

    MAPPING_FILE_DISPLAY_NAMES = {
        "brand_mapping.json": "品牌映射",
        "tag_jp_to_cn.json": "标签翻译 (DLsite日->中)",
        "tag_fanza_to_cn.json": "标签翻译 (Fanza日->中)",
        "tag_ggbase.json": "标签翻译 (GGBase->中)",
        "tag_mapping_dict.json": "标签合并规则",
        "bangumi_prop_mapping.json": "Bangumi属性映射",
        "genre_mapping.json": "游戏类型映射",
    }

    def __init__(self, parent=None):
        super().__init__("映射文件编辑器", parent)
        
        self.current_mapping_file = None
        self.current_data = {}
        self.mapping_dir = 'mapping'
        self._is_dirty = False

        # Main layout with margins for breathing room
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 15, 10, 10)
        main_layout.setSpacing(10)

        # Top controls for file selection
        top_form_layout = QFormLayout()
        top_form_layout.setSpacing(10)
        self.mapping_files_combo = QComboBox()
        top_form_layout.addRow("映射文件:", self.mapping_files_combo)
        main_layout.addLayout(top_form_layout)
        
        # Main editor area
        editor_splitter = QSplitter(Qt.Horizontal)
        
        # --- Left Side: Master List (Keys) ---
        master_widget = QWidget()
        master_layout = QVBoxLayout(master_widget)
        master_layout.setContentsMargins(0, 0, 0, 0)
        master_layout.setSpacing(5)

        master_title_layout = QHBoxLayout()
        master_title_layout.addWidget(QLabel("原始值 (Keys)"))
        master_title_layout.addStretch()
        
        # Create high-quality icons programmatically
        add_icon = create_plus_icon("#333333")
        delete_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)

        self.add_key_button = QPushButton()
        self.add_key_button.setIcon(add_icon)
        self.add_key_button.setObjectName("AddToolButton")
        self.add_key_button.setToolTip("添加新的原始值 (Key)")
        self.add_key_button.setFixedSize(28, 28)

        self.delete_key_button = QPushButton()
        self.delete_key_button.setObjectName("DangerToolButton")
        self.delete_key_button.setIcon(delete_icon)
        self.delete_key_button.setToolTip("删除选中的原始值 (Key)")
        self.delete_key_button.setFixedSize(28, 28)

        master_title_layout.addWidget(self.add_key_button)
        master_title_layout.addWidget(self.delete_key_button)
        master_layout.addLayout(master_title_layout)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索原始值...")
        master_layout.addWidget(self.search_input)

        self.master_list = QListWidget()
        master_layout.addWidget(self.master_list)
        
        # --- Right Side: Detail List (Values) ---
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(5)

        detail_title_layout = QHBoxLayout()
        detail_title_layout.addWidget(QLabel("映射值 (Values) - 双击修改"))
        detail_title_layout.addStretch()
        self.add_value_button = QPushButton()
        self.add_value_button.setIcon(add_icon)
        self.add_value_button.setObjectName("AddToolButton")
        self.add_value_button.setToolTip("为当前 Key 添加新值")
        self.add_value_button.setFixedSize(28, 28)

        self.delete_value_button = QPushButton()
        self.delete_value_button.setObjectName("DangerToolButton")
        self.delete_value_button.setIcon(delete_icon)
        self.delete_value_button.setToolTip("删除选中的值")
        self.delete_value_button.setFixedSize(28, 28)

        detail_title_layout.addWidget(self.add_value_button)
        detail_title_layout.addWidget(self.delete_value_button)
        detail_layout.addLayout(detail_title_layout)

        self.detail_list = QListWidget()
        self.detail_list.setAlternatingRowColors(True)
        detail_layout.addWidget(self.detail_list)
        
        # Add widgets to splitter
        editor_splitter.addWidget(master_widget)
        editor_splitter.addWidget(detail_widget)
        editor_splitter.setSizes([300, 450]) # Adjusted proportions
        main_layout.addWidget(editor_splitter, 1) # Make splitter stretch

        # Bottom save button
        bottom_layout = QHBoxLayout()
        self.save_button = QPushButton("💾 保存更改")
        self.save_button.setObjectName("PrimaryButton")
        apply_glow_effect(self.save_button, color="#1ABC9C", blur_radius=15, y_offset=2)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.save_button)
        main_layout.addLayout(bottom_layout)

        # Connect signals to slots
        self.mapping_files_combo.currentIndexChanged.connect(self.load_selected_file)
        self.master_list.currentItemChanged.connect(self.display_details)
        self.detail_list.itemDoubleClicked.connect(self.edit_detail_item)
        self.save_button.clicked.connect(self.save_current_file)
        self.add_key_button.clicked.connect(self.add_key)
        self.delete_key_button.clicked.connect(self.delete_key)
        self.add_value_button.clicked.connect(self.add_value)
        self.delete_value_button.clicked.connect(self.delete_value)
        self.search_input.returnPressed.connect(self.search_master_list)
        self.search_input.textChanged.connect(self.search_master_list)
        
        self.populate_mapping_files()

    @property
    def is_dirty(self):
        return self._is_dirty

    def set_dirty(self, dirty):
        if self._is_dirty == dirty:
            return
        self._is_dirty = dirty
        self.dirty_status_changed.emit(dirty)

    def search_master_list(self):
        search_text = self.search_input.text().lower()
        for i in range(self.master_list.count()):
            item = self.master_list.item(i)
            is_visible = not search_text or search_text in item.text().lower()
            item.setHidden(not is_visible)

    def populate_mapping_files(self):
        NON_EDITABLE_FILES = ['tag_ignore_list.json', 'bangumi_ignore_list.json', 'name_split_exceptions.json']
        try:
            if not os.path.isdir(self.mapping_dir):
                raise FileNotFoundError(f"Mapping directory '{self.mapping_dir}' not found.")
            
            files = [f for f in os.listdir(self.mapping_dir) if f.endswith('.json') and f not in NON_EDITABLE_FILES]
            
            self.mapping_files_combo.clear()
            for filename in sorted(files):
                display_name = self.MAPPING_FILE_DISPLAY_NAMES.get(filename, filename)
                self.mapping_files_combo.addItem(display_name, filename)

        except FileNotFoundError as e:
            self.log_message.emit(f"❌ 错误：{e}" + "\n")
            self.set_editor_enabled(False)

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
            d_ptr = result
            for part in parts[:-1]:
                if part not in d_ptr:
                    d_ptr[part] = {}
                d_ptr = d_ptr[part]
            d_ptr[parts[-1]] = value
        return result

    def load_selected_file(self, index=None):
        if self.is_dirty:
            # This part is complex, for now we just reset.
            # A proper implementation would ask the user to save.
            pass

        filename = self.mapping_files_combo.currentData()
        if not filename:
            return
            
        self.current_mapping_file = os.path.join(self.mapping_dir, filename)
        try:
            with open(self.current_mapping_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            self.log_message.emit(f"❌ 加载文件 '{filename}'失败: {e}" + "\n")
            data = {}
        
        self.master_list.clear()
        self.detail_list.clear()
        self.set_dirty(False)

        if isinstance(data, dict):
            self.current_data = self.flatten_dict(data)
            self.set_editor_enabled(True)
            sorted_keys = sorted(self.current_data.keys())
            self.master_list.addItems(sorted_keys)
            if sorted_keys:
                self.master_list.setCurrentRow(0)
        elif isinstance(data, list):
            self.log_message.emit(f"⚠️ 文件 '{os.path.basename(self.current_mapping_file)}' 是一个列表，当前编辑器不支持直接编辑。" + "\n")
            self.set_editor_enabled(False)
            self.detail_list.addItems([str(item) for item in data])
        else:
            self.set_editor_enabled(False)
            self.log_message.emit(f"❌ 不支持的数据格式: {type(data)}" + "\n")

    def display_details(self, current_item, _=None):
        self.detail_list.clear()
        if not current_item:
            return
        key = current_item.text()
        values = self.current_data.get(key, [])
        
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
            else:
                self.current_data[key] = new_value
            
            self.set_dirty(True)
            self.display_details(key_item)
            self.detail_list.setCurrentRow(row)
            self.log_message.emit(f"🔧 值已在界面中更新，请记得保存。" + "\n")

    def save_current_file(self):
        if not self.current_mapping_file:
            QMessageBox.warning(self, "没有文件", "没有选择要保存的文件。\n")
            return False
        
        try:
            unflattened_data = self.unflatten_dict(self.current_data)
            with open(self.current_mapping_file, 'w', encoding='utf-8') as f:
                json.dump(unflattened_data, f, indent=4, ensure_ascii=False)
            self.log_message.emit(f"✅ 文件 '{os.path.basename(self.current_mapping_file)}' 已成功保存。" + "\n")
            self.set_dirty(False)
            # self.load_selected_file() # No need to reload after saving
            return True
        except Exception as e:
            self.log_message.emit(f"❌ 保存文件失败: {e}" + "\n")
            QMessageBox.critical(self, "保存失败", f"无法保存文件: {e}" + "\n")
            return False

    def add_key(self):
        key, ok = QInputDialog.getText(self, "添加新键", "输入新的原始值 (Key), 可用 '.' 来创建层级:")
        if ok and key:
            if key in self.current_data:
                QMessageBox.warning(self, "键已存在", f"键 '{key}' 已存在。\n")
                return
            self.current_data[key] = [] 
            self.set_dirty(True)
            self.master_list.addItem(key)
            self.master_list.sortItems()
            items = self.master_list.findItems(key, Qt.MatchExactly)
            if items:
                self.master_list.setCurrentItem(items[0])
            self.log_message.emit(f"🔧 已添加新键 '{key}'，请为其添加值并保存。" + "\n")

    def delete_key(self):
        current_item = self.master_list.currentItem()
        if not current_item: return
        
        key = current_item.text()
        reply = QMessageBox.question(self, "确认删除", f"确定要删除键 '{key}' 及其所有映射值吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.master_list.takeItem(self.master_list.row(current_item))
            if key in self.current_data:
                del self.current_data[key]
                self.set_dirty(True)
            self.detail_list.clear()
            self.log_message.emit(f"🔧 已删除键 '{key}'，请记得保存。" + "\n")

    def add_value(self):
        current_key_item = self.master_list.currentItem()
        if not current_key_item:
            QMessageBox.warning(self, "没有选择键", "请先在左侧选择一个键。\n")
            return
        key = current_key_item.text()

        value, ok = QInputDialog.getText(self, "添加新值", f"为 '{key}' 添加新的映射值:")
        if ok and value:
            current_values = self.current_data.get(key)
            
            if not isinstance(current_values, list):
                current_values = [current_values] if current_values is not None and str(current_values).strip() != "" else []

            if value in [str(v) for v in current_values]:
                QMessageBox.warning(self, "值已存在", f"值 '{value}' 已经存在于 '{key}' 的映射中。\n")
                return
            
            current_values.append(value)
            self.current_data[key] = current_values
            self.set_dirty(True)
            self.display_details(current_key_item)
            self.log_message.emit(f"🔧 已为 '{key}' 添加值 '{value}'，请记得保存。" + "\n")

    def delete_value(self):
        current_key_item = self.master_list.currentItem()
        current_value_item = self.detail_list.currentItem()
        if not current_key_item or not current_value_item: return
        
        key = current_key_item.text()
        value_to_delete = current_value_item.text()
        
        current_values = self.current_data.get(key)
        
        if isinstance(current_values, list):
            reply = QMessageBox.question(self, "确认删除", f"确定要从 '{key}' 中删除值 '{value_to_delete}' 吗？",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                try:
                    index_to_del = -1
                    for i, v in enumerate(current_values):
                        if str(v) == value_to_delete:
                            index_to_del = i
                            break
                    
                    if index_to_del != -1:
                        current_values.pop(index_to_del)
                        self.current_data[key] = current_values
                        self.set_dirty(True)
                        self.display_details(current_key_item)
                        self.log_message.emit(f"🔧 已删除值 '{value_to_delete}'，请记得保存。" + "\n")
                except ValueError:
                    pass
        else:
             reply = QMessageBox.question(self, "确认删除", f"确定要删除 '{key}' 的值 '{value_to_delete}' 吗？ (这会清空该键的值)",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
             if reply == QMessageBox.Yes:
                self.current_data[key] = ""
                self.set_dirty(True)
                self.display_details(current_key_item)
                self.log_message.emit(f"🔧 已清空键 '{key}' 的值，请记得保存。" + "\n")
