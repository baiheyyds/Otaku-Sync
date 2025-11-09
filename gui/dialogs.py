from PySide6.QtCore import QPropertyAnimation, QRect, QSize, Qt, Slot
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.interaction import TYPE_SELECTION_MAP

from .image_loader import ImageLoader, get_placeholder_icon


class NameSplitterDialog(QDialog):
    def __init__(self, text, parts, parent=None):
        super().__init__(parent)
        self.setWindowTitle("高风险名称分割确认")
        self.setMinimumWidth(500)
        self.result = {"action": "keep", "save_exception": False} # Default

        layout = QVBoxLayout(self)
        info_group = QGroupBox("检测到可能不正确的名称分割")
        info_layout = QVBoxLayout(info_group)

        l1 = QLabel(f"<b>原始名称:</b> {text}")
        l1.setWordWrap(True)
        info_layout.addWidget(l1)

        l2 = QLabel(f"<b>初步分割为:</b> {parts}")
        l2.setWordWrap(True)
        info_layout.addWidget(l2)

        l3 = QLabel("原因: 分割后存在过短的部分，可能是误分割。\n请选择如何处理：")
        l3.setWordWrap(True)
        info_layout.addWidget(l3)

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

        label = QLabel(f"发现新的<b>【{source_name}】</b>标签: <b>{tag}</b>")
        label.setWordWrap(True)
        layout.addWidget(label)

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

        label = QLabel(f"请为新属性 '{prop_name}' 选择一个 Notion 类型：")
        label.setWordWrap(True)
        layout.addWidget(label)

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


class GameListItemWidget(QWidget):
    def __init__(self, image_loader, candidate_data, index, source, parent=None):
        super().__init__(parent)
        self.image_loader = image_loader
        self.thumbnail_url = None

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # 1. Image Label
        self.image_label = QLabel()
        self.image_size = QSize(150, 200)
        self.image_label.setFixedSize(self.image_size)
        self.image_label.setPixmap(get_placeholder_icon().pixmap(self.image_size))
        self.image_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.image_label)

        # Add a shadow effect to the cover image for depth
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(2, 2)
        self.image_label.setGraphicsEffect(shadow)

        # 2. Info Section (Right side)
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(5)

        title_font = QFont("Microsoft YaHei", 11)
        title_font.setBold(True)
        title_label = QLabel(f"{index}. {candidate_data.get('title', 'No Title')}")
        title_label.setFont(title_font)
        title_label.setWordWrap(True)

        if source == 'ggbases':
            size_info = candidate_data.get('容量', '未知')
            popularity = candidate_data.get('popularity', 0)
            info_text = f"热度: {popularity}<br>大小: {size_info}"
        else:
            price = candidate_data.get("价格") or candidate_data.get("price", "未知")
            price_display = f"{price}円" if str(price).isdigit() else price
            item_type = candidate_data.get("类型", "未知")
            info_text = f"💴 {price_display}<br>🏷️ {item_type}"

        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignTop)

        # Add widgets to info_layout with stretches for vertical vertical centering
        info_layout.addStretch(1)
        info_layout.addWidget(title_label)
        info_layout.addWidget(info_label)
        info_layout.addStretch(1)

        main_layout.addWidget(info_widget, 1)

        # 3. Load image
        thumbnail_url = candidate_data.get('thumbnail_url')
        if thumbnail_url:
            if thumbnail_url.startswith('//'):
                thumbnail_url = 'https:' + thumbnail_url
            self.thumbnail_url = thumbnail_url
            self.image_loader.load_image(thumbnail_url, self.on_image_loaded)

    @Slot(str, QPixmap)
    def on_image_loaded(self, url, pixmap):
        if self.thumbnail_url == url and not pixmap.isNull():
            # Create a new empty pixmap to draw on, with a transparent background
            scaled_pixmap = QPixmap(self.image_size)
            scaled_pixmap.fill(Qt.transparent)

            # Paint the downloaded pixmap onto the new one with high quality rendering
            painter = QPainter(scaled_pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

            # Calculate the target rectangle to maintain aspect ratio and center the image
            new_size = pixmap.size().scaled(self.image_size, Qt.KeepAspectRatio)
            x = (self.image_size.width() - new_size.width()) / 2
            y = (self.image_size.height() - new_size.height()) / 2

            target_rect = QRect(int(x), int(y), new_size.width(), new_size.height())

            painter.drawPixmap(target_rect, pixmap)
            painter.end()

            self.image_label.setPixmap(scaled_pixmap)

    def sizeHint(self):
        return QSize(super().sizeHint().width(), self.image_size.height() + 20) # Add padding


class SelectionDialog(QDialog):
    SEARCH_FANZA_ROLE = QDialogButtonBox.ActionRole

    def __init__(self, candidates, title="请选择", source="dlsite", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)

        # --- [新增] 淡入动画 ---
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(250)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        # --- [新增结束] ---

        self.image_loader = ImageLoader(self)

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()

        self.list_widget.setViewMode(QListWidget.ListMode)
        self.list_widget.setSpacing(5)
        self.list_widget.setMovement(QListWidget.Static)

        font = QFont("Microsoft YaHei", 10)
        self.list_widget.setFont(font)

        for i, candidate in enumerate(candidates):
            item_widget = GameListItemWidget(self.image_loader, candidate, i + 1, source)
            list_item = QListWidgetItem(self.list_widget)
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, i)
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, item_widget)

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

        # Adjust dialog size to content
        width = 800
        max_height = 800
        buttons_height = self.buttons.sizeHint().height()

        items_height = 0
        if self.list_widget.count() > 0:
            row_height = self.list_widget.sizeHintForRow(0)
            spacing = self.list_widget.spacing()
            items_height = (row_height * self.list_widget.count()) + (spacing * (self.list_widget.count() - 1))

        margins = layout.contentsMargins()
        total_content_height = items_height + buttons_height + margins.top() + margins.bottom() + 20

        final_height = min(max_height, total_content_height)
        min_height = 300
        final_height = max(min_height, final_height)

        self.resize(width, int(final_height))

    def showEvent(self, event):
        # --- [新增] 在显示时触发淡入动画 ---
        super().showEvent(event)
        # Set initial opacity to 0, otherwise it might flash
        self.opacity_effect.setOpacity(0)
        self.animation.start()
        # --- [新增结束] ---

    def handle_button_click(self, button):
        role = self.buttons.buttonRole(button)
        if role == self.SEARCH_FANZA_ROLE:
            self.done(2)

    def selected_index(self):
        if not self.list_widget.currentItem():
            return -1
        return self.list_widget.currentItem().data(Qt.UserRole)

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

class BrandMergeDialog(QDialog):
    def __init__(self, new_brand_name, suggested_brand, parent=None):
        super().__init__(parent)
        self.setWindowTitle("品牌查重确认")
        self.result = "cancel"  # Default to cancel

        layout = QVBoxLayout(self)

        # Use a QLabel with word wrap enabled for adaptive text
        text_label = QLabel(f"新品牌 '<b>{new_brand_name}</b>' 与已存在的品牌 '<b>{suggested_brand}</b>' 高度相似。\n\n您希望如何处理？")
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        # Button box for actions
        button_box = QDialogButtonBox()
        merge_button = button_box.addButton("合并为 ‘" + suggested_brand + "’ (推荐)", QDialogButtonBox.AcceptRole)
        create_button = button_box.addButton("创建新品牌 ‘" + new_brand_name + "’", QDialogButtonBox.ActionRole)
        cancel_button = button_box.addButton("取消操作", QDialogButtonBox.RejectRole)

        merge_button.clicked.connect(self.on_merge)
        create_button.clicked.connect(self.on_create)
        cancel_button.clicked.connect(self.on_cancel)

        layout.addWidget(button_box)

        # Set a reasonable initial size; the layout will manage the rest
        self.resize(500, 150)

    def on_merge(self):
        self.result = "merge"
        self.accept()

    def on_create(self):
        self.result = "create"
        self.accept()

    def on_cancel(self):
        self.result = "cancel"
        self.reject()

class ConceptMergeDialog(QDialog):
    def __init__(self, concept, candidate, parent=None):
        super().__init__(parent)
        self.setWindowTitle("标签概念合并确认")
        self.result = "cancel" # Default to cancel

        layout = QVBoxLayout(self)
        text_label = QLabel(f"新标签概念 '<b>{concept}</b>' 与现有标签 '<b>{candidate}</b>' 高度相似。\n\n是否要将新概念合并到现有标签中？")
        text_label.setWordWrap(True)
        layout.addWidget(text_label)

        button_box = QDialogButtonBox()
        merge_button = button_box.addButton("合并 (推荐)", QDialogButtonBox.AcceptRole)
        create_button = button_box.addButton("创建为新标签", QDialogButtonBox.ActionRole)
        cancel_button = button_box.addButton("取消", QDialogButtonBox.RejectRole)

        merge_button.clicked.connect(self.on_merge)
        create_button.clicked.connect(self.on_create)
        cancel_button.clicked.connect(self.on_cancel)

        layout.addWidget(button_box)
        self.resize(500, 150)

    def on_merge(self):
        self.result = "merge"
        self.accept()

    def on_create(self):
        self.result = "create"
        self.accept()

    def on_cancel(self):
        self.result = "cancel"
        self.reject()
