import sys
import os
import importlib.util
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem, 
                             QListWidget, QListWidgetItem, QSplitter, QVBoxLayout, 
                             QWidget, QPushButton, QFileDialog, QTextEdit, QHBoxLayout,
                             QMessageBox, QAbstractItemView, QMenu, QLabel, QLineEdit)
from PyQt6.QtCore import Qt, QMimeData, QDataStream, QIODevice, pyqtSignal, QByteArray, QPoint
from PyQt6.QtGui import QDrag, QIcon
import uuid

# 定义MIME类型
MIME_TYPE = "application/x-test-item"


class StepObject:
    """Represent a step in the sequence. Holds parameters as attributes so each
    dropped item owns its own param state.

    Attributes:
        id: unique id
        type: 'function' or 'control'
        module: module name (for functions)
        function: function name (for functions)
        control: control token (for control items)
        params: dict of parameter name -> string value
    """
    def __init__(self, type_, module=None, function=None, control=None):
        self.id = str(uuid.uuid4())
        self.type = type_
        self.module = module
        self.function = function
        self.control = control
        self.params = {}


class DraggableTreeWidget(QTreeWidget):
    """可拖拽的函数列表"""
    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setHeaderLabel("测试函数")
        self.drag_start_position = QPoint(0, 0)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.position().toPoint()
        super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.position().toPoint() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return
            
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # 获取当前选中项
        current_item = self.currentItem()
        if current_item and current_item.parent():  # 确保是函数而不是模块
            # 创建自定义数据格式
            item_data = QByteArray()
            data_stream = QDataStream(item_data, QIODevice.OpenModeFlag.WriteOnly)
            data_stream.writeString(current_item.text(0).encode('utf-8'))
            data_stream.writeString(current_item.parent().text(0).encode('utf-8'))
            
            mime_data.setData(MIME_TYPE, item_data)
            drag.setMimeData(mime_data)
            
            drag.exec(Qt.DropAction.CopyAction)

class DroppableListWidget(QListWidget):
    """可接收拖拽的测试序列列表"""
    itemMoved = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE) or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)
            
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE) or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)
            
    def dropEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE):
            item_data = event.mimeData().data(MIME_TYPE)
            data_stream = QDataStream(item_data, QIODevice.OpenModeFlag.ReadOnly)
            func_name = bytes(data_stream.readString()).decode('utf-8')
            module_name = bytes(data_stream.readString()).decode('utf-8')
            
            item = QListWidgetItem(f"{module_name}.{func_name}")
            step = StepObject(type_="function", module=module_name, function=func_name)
            item.setData(Qt.ItemDataRole.UserRole, step)
            item.setData(Qt.ItemDataRole.UserRole + 1, step.id)  # 唯一ID
            self.addItem(item)
            event.acceptProposedAction()
        elif event.mimeData().hasText():
            text = event.mimeData().text()
            if text in ["if", "for", "end"]:
                item = QListWidgetItem(text)
                step = StepObject(type_="control", control=text)
                item.setData(Qt.ItemDataRole.UserRole, step)
                item.setData(Qt.ItemDataRole.UserRole + 1, step.id)  # 唯一ID
                self.addItem(item)
                event.acceptProposedAction()
        else:
            super().dropEvent(event)
        self.itemMoved.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.currentItem():
            row = self.currentRow()
            item = self.takeItem(row)
            del item
            self.itemMoved.emit()  # 触发更新
        else:
            super().keyPressEvent(event)

class ControlWidget(QWidget):
    """控制语句部件"""
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        layout = QHBoxLayout(self)
        
        self.if_button = QPushButton("If")
        self.for_button = QPushButton("For")
        self.end_button = QPushButton("End")
        
        # 设置可拖拽
        self.if_button.setMouseTracking(True)
        self.for_button.setMouseTracking(True)
        self.end_button.setMouseTracking(True)
        
        layout.addWidget(self.if_button)
        layout.addWidget(self.for_button)
        layout.addWidget(self.end_button)
        
        # 连接信号
        self.if_button.pressed.connect(lambda: self.start_drag("if"))
        self.for_button.pressed.connect(lambda: self.start_drag("for"))
        self.end_button.pressed.connect(lambda: self.start_drag("end"))
        
    def start_drag(self, text):
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(text)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.test_functions = {}
        self.current_param_widgets = {}  # 缓存当前参数控件
        self.step_params_cache = {}      # 缓存每个步骤的参数值，key: "module.func", value: dict
        self.init_ui()
        self.load_test_functions()
        self.create_menu_bar()  # 确保方法已定义

    def create_menu_bar(self):
        """创建菜单栏"""
        menu_bar = self.menuBar()

        # File 菜单
        file_menu = menu_bar.addMenu('File')
        load_action = file_menu.addAction('Load Test Functions')
        load_action.triggered.connect(self.load_test_functions)

        clear_action = file_menu.addAction('Clear Sequence')
        clear_action.triggered.connect(self.clear_sequence)

        file_menu.addSeparator()
        exit_action = file_menu.addAction('Exit')
        exit_action.triggered.connect(self.close)

        # Edit 菜单
        edit_menu = menu_bar.addMenu('Edit')

        # View 菜单
        view_menu = menu_bar.addMenu('View')

        # Execute 菜单
        execute_menu = menu_bar.addMenu('Execute')
        run_action = execute_menu.addAction('Run Test Sequence')
        run_action.triggered.connect(self.run_sequence)

        # Debug 菜单
        debug_menu = menu_bar.addMenu('Debug')

        # Configure 菜单
        config_menu = menu_bar.addMenu('Configure')

        # Tools 菜单
        tools_menu = menu_bar.addMenu('Tools')

        # Window 和 Help 菜单
        window_menu = menu_bar.addMenu('Window')
        help_menu = menu_bar.addMenu('Help')

    def init_ui(self):
        self.setWindowTitle("测试序列运行器")
        self.setGeometry(100, 100, 1000, 600)
        
        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(main_splitter)
        
        # 左侧区域
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # 函数树
        self.function_tree = DraggableTreeWidget()
        left_layout.addWidget(self.function_tree)
        
        # 控制语句区域
        self.control_widget = ControlWidget()
        left_layout.addWidget(self.control_widget)
        
        # 右侧区域
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # 测试序列列表
        self.sequence_list = DroppableListWidget()
        right_layout.addWidget(self.sequence_list)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        self.load_button = QPushButton("加载测试函数")
        self.run_button = QPushButton("运行测试序列")
        self.clear_button = QPushButton("清空序列")
        
        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.clear_button)
        
        right_layout.addLayout(button_layout)
        
        # --- 步骤设置区域 ---
        self.step_config_group = QWidget()
        step_layout = QVBoxLayout(self.step_config_group)
        step_layout.setContentsMargins(5, 5, 5, 5)
        
        self.current_param_widgets = {}  # 缓存当前参数控件
        
        step_layout.addWidget(QLabel("<b>步骤设置</b>"))
        
        # 输入参数区
        self.input_params_layout = QVBoxLayout()
        self.input_params_widget = QWidget()
        self.input_params_widget.setLayout(self.input_params_layout)
        step_layout.addWidget(QLabel("输入参数:"))
        step_layout.addWidget(self.input_params_widget)
        
        # 输出参数区
        self.output_params_label = QLabel("-")
        self.output_params_label.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 5px; border: 1px solid #ccc; }")
        step_layout.addWidget(QLabel("输出参数:"))
        step_layout.addWidget(self.output_params_label)
        
        right_layout.addWidget(self.step_config_group)
        
        # 输出区域
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        right_layout.addWidget(self.output_text)
        
        # 添加到分割器
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)
        main_splitter.setSizes([300, 700])
        
        # 连接信号
        self.load_button.clicked.connect(self.load_test_functions)
        self.run_button.clicked.connect(self.run_sequence)
        self.clear_button.clicked.connect(self.clear_sequence)
        self.sequence_list.itemMoved.connect(self.update_output)
        # 使用 currentItemChanged 来获取上一个选中项（previous）以便在切换时保存它的参数
        self.sequence_list.currentItemChanged.connect(self.on_current_item_changed)

    def on_current_item_changed(self, current, previous):
        """在选中项变化时触发：先保存 previous 的参数，然后为 current 显示/恢复参数"""
        # 保存之前选中项的参数（如果有）
        if previous:
            self.save_current_params(previous)

        # 清除旧输入框
        self.clear_param_inputs()

        if not current:
            self.output_params_label.setText("-")
            return

        print(f"[DEBUG] 当前已选测试项: {current.text()}")
        data = current.data(Qt.ItemDataRole.UserRole)
        # 支持新的 StepObject 或旧的 dict（向后兼容）
        if isinstance(data, StepObject):
            item_id = data.id
            print(f"[DEBUG] 当前项唯一ID: {item_id}")
            print(f"[DEBUG] 当前项参数: {data.params}")
            is_function = (data.type == "function")
            module_name = data.module
            func_name = data.function
            func = self.test_functions.get(module_name, {}).get(func_name) if is_function else None
        else:
            item_id = current.data(Qt.ItemDataRole.UserRole + 1)
            print(f"[DEBUG] 当前项唯一ID: {item_id}")
            print(f"[DEBUG] 当前缓存内容: {list(self.step_params_cache.keys())}")
            is_function = data.get("type") == "function"
            module_name = data.get("module") if is_function else None
            func_name = data.get("function") if is_function else None
            func = self.test_functions.get(module_name, {}).get(func_name) if is_function else None

        if is_function:
            if func is None:
                self.add_input_row("error", "函数未找到", read_only=True)
                return

            import inspect
            try:
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())

                # 创建输入框，并填入该item专属的缓存值（从 StepObject.params 或旧缓存读取）
                for param_name in params:
                    if isinstance(data, StepObject):
                        cached_value = data.params.get(param_name, "")
                    else:
                        cached_value = self.step_params_cache.get(item_id, {}).get(param_name, "")
                    print(f"[DEBUG] 参数 '{param_name}' 的缓存值: '{cached_value}'")  # 调试
                    edit = self.add_input_row(param_name, cached_value)
                    # 连接实时修改：当用户修改输入框时更新该项的 StepObject.params
                    if isinstance(data, StepObject):
                        # connect after creation
                        edit.textChanged.connect(lambda val, it=current, p=param_name: self.on_param_changed(it, p, val))

                # 显示输出参数
                return_annotation = sig.return_annotation
                if return_annotation != inspect.Signature.empty:
                    if hasattr(return_annotation, '__name__'):
                        output_name = return_annotation.__name__
                    else:
                        output_name = str(return_annotation)
                    self.output_params_label.setText(output_name)
                else:
                    self.output_params_label.setText("未知（无类型注解）")
            except Exception as e:
                self.add_input_row("error", f"解析失败: {str(e)}", read_only=True)
        else:
            self.output_params_label.setText("-")

    def load_test_functions(self):
        """加载当前目录下的测试函数"""
        self.function_tree.clear()
        self.test_functions = {}
        
        # 查找当前目录下的Python文件
        current_dir = os.getcwd()
        for file in os.listdir(current_dir):
            if file.endswith(".py") and file.startswith("test_") and file != "test_functions.py":
                module_name = file[:-3]  # 移除.py扩展名
                try:
                    spec = importlib.util.spec_from_file_location(module_name, file)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # 获取模块中的函数
                    functions = []
                    for name in dir(module):
                        if callable(getattr(module, name)) and not name.startswith("_"):
                            functions.append(name)
                            # 保存函数引用
                            if module_name not in self.test_functions:
                                self.test_functions[module_name] = {}
                            self.test_functions[module_name][name] = getattr(module, name)
                    
                    # 添加到函数树
                    if functions:
                        module_item = QTreeWidgetItem([module_name])
                        self.function_tree.addTopLevelItem(module_item)
                        for func_name in functions:
                            func_item = QTreeWidgetItem([func_name])
                            module_item.addChild(func_item)
                except Exception as e:
                    print(f"无法加载模块 {module_name}: {e}")
        
        self.function_tree.expandAll()
        
    def clear_sequence(self):
        """清空测试序列"""
        self.sequence_list.clear()
        self.update_output()
        
    def update_output(self):
        """更新输出显示"""
        sequence_text = "当前测试序列:\n"
        for i in range(self.sequence_list.count()):
            item = self.sequence_list.item(i)
            sequence_text += f"{i+1}. {item.text()}\n"
        self.output_text.setText(sequence_text)
        
    def run_sequence(self):
        """运行测试序列"""
        output = "开始执行测试序列...\n"
        self.output_text.setText(output)
        QApplication.processEvents()  # 更新界面

        try:
            # 执行序列中的每一项
            for i in range(self.sequence_list.count()):
                item = self.sequence_list.item(i)
                step_data = item.data(Qt.ItemDataRole.UserRole)

                # Determine whether this is a function step or control step
                is_function = False
                func = None
                module_name = None
                func_name = None
                if isinstance(step_data, StepObject):
                    if step_data.type == "function":
                        is_function = True
                        module_name = step_data.module
                        func_name = step_data.function
                        func = self.test_functions.get(module_name, {}).get(func_name)
                    else:
                        # control
                        output += f"控制语句: {step_data.control}\n"
                        self.output_text.setText(output)
                        QApplication.processEvents()
                        continue
                else:
                    # legacy dict-based storage
                    if step_data.get("type") == "function":
                        is_function = True
                        module_name = step_data.get("module")
                        func_name = step_data.get("function")
                        func = self.test_functions.get(module_name, {}).get(func_name)
                    elif step_data.get("type") == "control":
                        output += f"控制语句: {step_data.get('control')}\n"
                        self.output_text.setText(output)
                        QApplication.processEvents()
                        continue

                if is_function:
                    output += f"执行: {module_name}.{func_name}... "
                    self.output_text.setText(output)
                    QApplication.processEvents()

                    if func is None:
                        output += "函数未找到\n"
                        self.output_text.setText(output)
                        continue

                    # 获取函数签名，准备参数
                    import inspect
                    sig = inspect.signature(func)
                    params = sig.parameters
                    args = {}

                    # 从 step_data 或当前输入框提取参数值，并做类型转换
                    for param_name in params.keys():
                        if isinstance(step_data, StepObject):
                            value_str = step_data.params.get(param_name, '').strip()
                        else:
                            if param_name in self.current_param_widgets:
                                widget = self.current_param_widgets[param_name]
                                value_str = widget.text().strip()
                            else:
                                value_str = ''

                        # 类型转换
                        param_type = params[param_name].annotation
                        if param_type != inspect.Parameter.empty:
                            try:
                                if param_type == bool:
                                    value = value_str.lower() in ('true', '1', 'yes', 'on')
                                elif param_type in (int, float):
                                    value = param_type(value_str)
                                else:
                                    value = value_str  # 默认作为字符串
                            except Exception as e:
                                output += f"参数 '{param_name}' 类型转换失败: {e}\n"
                                self.output_text.setText(output)
                                QApplication.processEvents()
                                continue
                        else:
                            value = value_str  # 无类型注解时作为字符串
                        args[param_name] = value

                    # 调用函数
                    try:
                        result = func(**args)
                        output += f"{'成功' if result is None or result else '失败'}\n"
                    except Exception as e:
                        output += f"错误: {str(e)}\n"
                    
                self.output_text.setText(output)
                QApplication.processEvents()
                
            output += "测试序列执行完成。\n"
            self.output_text.setText(output)
            
        except Exception as e:
            output += f"执行过程中发生错误: {str(e)}\n"
            self.output_text.setText(output)

    def add_input_row(self, param_name, default_value="", read_only=False):
        """添加一行参数输入，并输出调试信息"""
        print(f"[DEBUG] 创建输入框: {param_name} = '{default_value}'")
        row_layout = QHBoxLayout()
        label = QLabel(f"{param_name}:")
        label.setFixedWidth(100)
        edit = QLineEdit(str(default_value))
        edit.setReadOnly(read_only)
        row_layout.addWidget(label)
        row_layout.addWidget(edit)
        self.input_params_layout.addLayout(row_layout)
        self.current_param_widgets[param_name] = edit
        print(f"[DEBUG] QLineEdit.text() after set: '{edit.text()}'")
        edit.repaint()
        edit.update()
        return edit
        
    def clear_param_inputs(self):
        """清除所有参数输入框"""
        while self.input_params_layout.count():
            child = self.input_params_layout.takeAt(0)
            if child.layout():
                while child.layout().count():
                    widget = child.layout().takeAt(0).widget()
                    if widget:
                        widget.deleteLater()
        self.current_param_widgets.clear()  # 确保控件映射也被清除
        self.output_params_label.setText("-")

    def save_current_params(self, item=None):
        """保存指定 item（或当前项）的参数到缓存。

        Args:
            item (QListWidgetItem|None): 要保存的项；为 None 时使用当前项。
        """
        current_item = item or self.sequence_list.currentItem()
        if not current_item or not self.current_param_widgets:
            return

        # 获取item的唯一ID
        item_id = current_item.data(Qt.ItemDataRole.UserRole + 1)
        if not item_id:
            return

        if item_id not in self.step_params_cache:
            self.step_params_cache[item_id] = {}

        # 如果 item 使用 StepObject，则把值保存到该对象的 params；否则回退到旧的 step_params_cache
        data = current_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, StepObject):
            for param_name, widget in self.current_param_widgets.items():
                data.params[param_name] = widget.text()
        else:
            if item_id not in self.step_params_cache:
                self.step_params_cache[item_id] = {}
            for param_name, widget in self.current_param_widgets.items():
                self.step_params_cache[item_id][param_name] = widget.text()

    def on_param_changed(self, item, param_name, value):
        """Callback when a parameter input changes — update the StepObject for the given item."""
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, StepObject):
            data.params[param_name] = value

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()