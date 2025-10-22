import asyncio
import logging
import threading

from PySide6.QtCore import QEvent, Qt
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.cache_warmer import warm_up_brand_cache_standalone
from core.context_factory import create_shared_context
from core.gui_worker import GameSyncWorker, ScriptWorker
from core.init import close_context
from utils.gui_bridge import log_bridge

# Import dialogs and widgets from the new GUI package
from .dialogs import (
    BangumiMappingDialog,
    BangumiSelectionDialog,
    BrandMergeDialog,
    ConceptMergeDialog,
    DuplicateConfirmationDialog,
    NameSplitterDialog,
    PropertyTypeDialog,
    SelectionDialog,
    TagTranslationDialog,
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
        top_layout.addWidget(QLabel("请输入游戏名:"))
        top_layout.addWidget(self.keyword_input, 1)
        top_layout.addWidget(self.manual_mode_checkbox)
        top_layout.addWidget(self.search_button)
        main_layout.addLayout(top_layout)

        # Main splitter for controls and log
        main_splitter = QSplitter(Qt.Horizontal)

        # --- New Tab-based layout for controls ---
        self.tab_widget = QTabWidget()
        self.batch_tools_widget = BatchToolsWidget()
        self.mapping_editor_widget = MappingEditorWidget()

        self.tab_widget.addTab(self.batch_tools_widget, "批处理工具")
        self.tab_widget.addTab(self.mapping_editor_widget, "映射文件编辑器")
        # --- End of new Tab layout ---

        # Bottom widget for the log console
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.addWidget(QLabel("运行日志"))
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        log_layout.addWidget(self.log_console)

        main_splitter.addWidget(self.tab_widget) # Add tab widget instead of the old controls widget
        main_splitter.addWidget(log_widget)

        # Adjust splitter ratio for an initial 50/50 split
        main_splitter.setSizes([int(self.width() * 0.5), int(self.width() * 0.5)])
        main_layout.addWidget(main_splitter)

        # --- Progress and Status Bar Widgets ---
        self.statusBar() # Ensure status bar exists
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setTextVisible(False) # Text will be in progress_label
        self.progress_bar.setFixedWidth(200) # Fixed width for aesthetics
        self.progress_bar.setVisible(False)

        self.progress_label = QLabel("准备就绪")
        self.progress_label.setVisible(False)

        self.time_label = QLabel("耗时: 0.00秒")
        self.time_label.setVisible(False)

        self.statusBar().addPermanentWidget(self.progress_label)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.statusBar().addPermanentWidget(self.time_label)
        # --- End Progress and Status Bar Widgets ---

        # Setup logging
        log_bridge.log_received.connect(self.log_console.appendPlainText)
        # Connect the mapping editor's log signal
        self.mapping_editor_widget.log_message.connect(self.log_console.appendPlainText)
        self.mapping_editor_widget.dirty_status_changed.connect(self.update_window_title)

        self.init_shared_context()
        self.run_background_tasks()

        logging.info("✅ 初始化完成，可以开始使用.\n")

        # Connect signals
        self.search_button.clicked.connect(self.start_search_process)
        self.keyword_input.returnPressed.connect(self.start_search_process)
        self.batch_tools_widget.script_triggered.connect(self.start_script_execution)

    def update_window_title(self, is_dirty):
        title = "Otaku Sync - 图形工具"
        if is_dirty:
            title += " *"
        self.setWindowTitle(title)

    # --- New Slots for Progress and Timing ---
    def handle_progress_start(self, max_value):
        self.progress_bar.setMaximum(max_value)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.progress_label.setText("正在准备...")
        self.progress_label.setVisible(True)
        self.time_label.setText("耗时: 0.00秒")
        self.time_label.setVisible(True)
        self.start_time = self.current_time_in_seconds() # Initialize start time

    def handle_progress_update(self, current_value, text):
        self.progress_bar.setValue(current_value)
        self.progress_label.setText(text)
        elapsed = self.current_time_in_seconds() - self.start_time
        self.time_label.setText(f"耗时: {elapsed:.2f}秒")

    def handle_time_update(self, elapsed_time_string):
        self.time_label.setText(elapsed_time_string)

    def handle_progress_finish(self):
        self.progress_bar.setValue(self.progress_bar.maximum()) # Ensure it shows 100%
        self.progress_label.setText("任务完成")
        elapsed = self.current_time_in_seconds() - self.start_time
        self.time_label.setText(f"总耗时: {elapsed:.2f}秒")
        # Hide after a short delay for better UX
        QTimer.singleShot(3000, self._hide_progress_widgets)

    def _hide_progress_widgets(self):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.time_label.setVisible(False)

    def current_time_in_seconds(self):
        import time
        return time.time()

    def init_shared_context(self):
        logging.info("🔧 正在初始化应用程序级共享上下文...")
        self.shared_context = create_shared_context()

        # 程序启动时，在后台预创建所需的浏览器驱动
        if self.shared_context.get("driver_factory"):
            logging.info("🚀 在后台预启动浏览器驱动...")
            driver_factory = self.shared_context["driver_factory"]
            driver_factory.start_background_creation(["dlsite_driver", "ggbases_driver"])

        logging.info("✅ 应用程序级共享上下文已准备就绪.\n")

    def run_background_tasks(self):
        # Wrapper to run asyncio code in a separate thread
        def run_async_task(task):
            try:
                asyncio.run(task)
            except Exception as e:
                # Log errors to the main log file, but don't interact with GUI
                logging.error(f"❌ 后台任务执行失败: {e}", exc_info=True)

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
            logging.info("🔧 主窗口已接收并保存共享的应用上下文.\n")
            self.shared_context = context

    def start_search_process(self):
        if self.is_worker_running():
            return
        keyword = self.keyword_input.text().strip()
        if not keyword:
            logging.warning("⚠️ 请输入游戏名/关键词后再开始搜索.\n")
            return

        self.set_all_buttons_enabled(False)
        self.search_button.setText("正在运行...")
        self.log_console.clear()
        manual_mode = self.manual_mode_checkbox.isChecked()

        self.game_sync_worker = GameSyncWorker(keyword=keyword, manual_mode=manual_mode, shared_context=self.shared_context, parent=self)
        self.connect_game_sync_signals(self.game_sync_worker)
        self.game_sync_worker.start()

    def start_script_execution(self, script_func, script_name):
        if self.is_worker_running():
            return

        logging.info(f"🚀 即将执行脚本: {script_name}")
        self.log_console.clear()
        self.set_all_buttons_enabled(False)

        self.script_worker = ScriptWorker(script_func, script_name, shared_context=self.shared_context, parent=self)
        self.connect_script_signals(self.script_worker)
        self.script_worker.start()


    def is_worker_running(self, silent=False):
        if self.game_sync_worker and self.game_sync_worker.isRunning() or self.script_worker and self.script_worker.isRunning():
            if not silent:
                QMessageBox.warning(self, "任务正在进行", "请等待当前任务完成.\n")
            return True
        return False

    def _connect_common_signals(self, worker):
        """Connects signals that are common to both worker types."""
        worker.context_created.connect(self.set_shared_context)
        worker.bangumi_mapping_required.connect(self.handle_bangumi_mapping)
        worker.property_type_required.connect(self.handle_property_type)
        worker.bangumi_selection_required.connect(self.handle_bangumi_selection_required)
        worker.tag_translation_required.connect(self.handle_tag_translation_required)
        worker.concept_merge_required.connect(self.handle_concept_merge_required)
        worker.name_split_decision_required.connect(self.handle_name_split_decision_required)
        worker.confirm_brand_merge_requested.connect(self.handle_brand_merge_requested)
        worker.finished.connect(self.cleanup_worker)

        # Connect progress and timing signals
        worker.progress_start.connect(self.handle_progress_start)
        worker.progress_update.connect(self.handle_progress_update)
        worker.time_update.connect(self.handle_time_update)
        worker.progress_finish.connect(self.handle_progress_finish)

    def connect_script_signals(self, worker):
        """Connects signals for a generic ScriptWorker."""
        self._connect_common_signals(worker)
        worker.script_completed.connect(self.on_script_completed)

    def connect_game_sync_signals(self, worker):
        """Connects all signals for the specialized GameSyncWorker."""
        self._connect_common_signals(worker)
        # Connect signals specific to GameSyncWorker
        worker.selection_required.connect(self.handle_selection_required)
        worker.duplicate_check_required.connect(self.handle_duplicate_check)
        worker.process_completed.connect(self.process_finished)

    def on_script_completed(self, script_name, success, result):
        logging.info(f'✅ 脚本 "{script_name}" 执行结束，结果: {"成功" if success else "失败"}\n')
        # Only re-enable all buttons if it was a user-initiated script
        # The initial stats load runs in the background and shouldn't affect button state.
        if self.sender() and self.sender().parent() == self: # Check if it's a main worker
            self.set_all_buttons_enabled(True)

        if not success:
            return

        elif script_name == "导出所有品牌名" and isinstance(result, list):
            output_filename = "brand_names.txt"
            try:
                with open(output_filename, "w", encoding="utf-8") as f:
                    for name in result:
                        f.write(name + "\n")
                QMessageBox.information(self, "导出成功",
                                        f"已成功导出 {len(result)} 个品牌名到项目根目录下的\n"
                                        f"{output_filename} 文件中。 ")
            except IOError as e:
                logging.error(f"❌ 写入文件 {output_filename} 时出错: {e}")
                QMessageBox.critical(self, "文件写入失败", f"无法写入品牌列表到 {output_filename} ")

    def set_all_buttons_enabled(self, enabled):
        self.search_button.setEnabled(enabled)
        self.search_button.setText("🔍 开始搜索" if enabled else "正在运行...")
        self.batch_tools_widget.set_buttons_enabled(enabled)
        # self.statistics_widget.refresh_button.setEnabled(enabled)

    # --- All handler methods for dialogs --- #

    def handle_brand_merge_requested(self, new_brand_name, suggested_brand):
        logging.info(f"🔍 检测到相似品牌: ‘{new_brand_name}’ ≈ ‘{suggested_brand}’")
        worker = self.sender()
        if not worker:
            return

        dialog = BrandMergeDialog(new_brand_name, suggested_brand, self)
        dialog.exec()

        # The dialog's result property holds the user's choice
        worker.set_interaction_response(dialog.result)

    def handle_name_split_decision_required(self, text, parts):
        logging.info(f"🔍 需要为名称 '{text}' 的分割方式 '{parts}' 做出决策...")
        dialog = NameSplitterDialog(text, parts, self)
        worker = self.sender()
        if dialog.exec() == QDialog.Accepted:
            worker.set_interaction_response(dialog.result)
        else:
            worker.set_interaction_response({"action": "keep", "save_exception": False})

    def handle_tag_translation_required(self, tag, source_name):
        logging.info(f"🔍 需要为新标签 '{tag}' ({source_name}) 提供翻译...")
        dialog = TagTranslationDialog(tag, source_name, self)
        worker = self.sender()
        if dialog.exec() == QDialog.Accepted:
            worker.set_interaction_response(dialog.result)
        else:
            worker.set_interaction_response("s") # Treat cancel as skip

    def handle_concept_merge_required(self, concept, candidate):
        logging.info(f"🔍 需要为新概念 '{concept}' 选择合并策略...")
        worker = self.sender()
        if not worker:
            return

        dialog = ConceptMergeDialog(concept, candidate, self)
        dialog.exec()
        worker.set_interaction_response(dialog.result)

    def handle_bangumi_selection_required(self, game_name, candidates):
        logging.info("🔧 [GUI] Received bangumi_selection_required, creating dialog.")
        dialog = BangumiSelectionDialog(game_name, candidates, self)
        worker = self.sender()

        result = dialog.exec()

        if result == QDialog.Accepted:
            worker.set_interaction_response(dialog.selected_id)
        else:
            worker.set_interaction_response(None)

    def handle_bangumi_mapping(self, request_data):
        logging.info("🔧 需要进行 Bangumi 属性映射，等待用户操作...\n")
        dialog = BangumiMappingDialog(request_data, self)
        dialog.exec()
        self.sender().set_interaction_response(dialog.result)

    def handle_property_type(self, request_data):
        logging.info(f"🔧 需要为新属性 '{request_data['prop_name']}' 选择类型...\n")
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
            logging.warning("⚠️ 未找到任何结果.\n")
            worker.set_interaction_response(None)
            return

        logging.info(f"🔍 接收到 {len(choices)} 个选项，请在弹出对话框中选择...\n")
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
            logging.info(f"🔍 用户选择了第 {choice_index + 1} 项。\n")
            worker.set_interaction_response(choice_index)
        elif result == 2: # Custom result code for 'Search Fanza'
            logging.info("🔍 用户选择切换到 Fanza 搜索...\n")
            worker.set_interaction_response("search_fanza")
        else:
            logging.info("🔍 用户取消了选择。\n")
            worker.set_interaction_response(-1)

    def handle_duplicate_check(self, candidates):
        worker = self.sender()
        if not worker:
            return

        logging.info("🔍 发现可能重复的游戏，等待用户确认...\n")
        dialog = DuplicateConfirmationDialog(candidates, self)
        dialog.exec()
        choice = dialog.result
        logging.info(f"🔍 用户对重复游戏的操作是: {choice}\n")
        worker.set_interaction_response(choice)

    def process_finished(self, success):
        logging.info(f'✅ 任务完成，结果: {"成功" if success else "失败"}\n')
        self.set_all_buttons_enabled(True)

    def cleanup_worker(self):
        logging.info("🔧 后台线程已退出，正在清理...\n")
        sender = self.sender()
        if sender == self.game_sync_worker:
            self.game_sync_worker.deleteLater()
            self.game_sync_worker = None
        elif sender == self.script_worker:
            self.script_worker.deleteLater()
            self.script_worker = None

    def closeEvent(self, event):
        # First, check for unsaved changes in the mapping editor
        if self.mapping_editor_widget.is_dirty:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle('未保存的更改')
            msg_box.setText("映射文件有未保存的更改。您想在退出前保存吗？")
            msg_box.setIcon(QMessageBox.Question)

            save_button = msg_box.addButton("保存", QMessageBox.AcceptRole)
            discard_button = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
            cancel_button = msg_box.addButton("取消", QMessageBox.RejectRole)

            msg_box.setDefaultButton(cancel_button)
            msg_box.exec()

            clicked_button = msg_box.clickedButton()

            if clicked_button == save_button:
                if not self.mapping_editor_widget.save_current_file():
                    event.ignore() # Ignore exit if save failed
                    return
            elif clicked_button == cancel_button:
                event.ignore()
                return
            # If discard_button is clicked, just proceed

        # Then, check for running workers
        if (self.game_sync_worker and self.game_sync_worker.isRunning()) or \
           (self.script_worker and self.script_worker.isRunning()):
            reply = QMessageBox.question(self, '任务正在进行',
                                       "当前有任务正在后台运行，强制退出可能导致数据不一致或浏览器进程残留。\n\n确定要退出吗？",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                logging.warning("⚠️ 用户选择强制退出。\n")
            else:
                event.ignore()
                return

        logging.info("🔧 正在清理应用资源并保存所有数据...")
        if self.shared_context:
            try:
                asyncio.run(close_context(self.shared_context))
            except Exception as e:
                logging.error(f"❌ 关闭应用时发生错误: {e}")

        logging.info("🔧 程序已安全退出。\n")
        event.accept()
