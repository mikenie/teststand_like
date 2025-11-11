import sys
import os
import importlib.util
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem, 
                             QListWidget, QListWidgetItem, QSplitter, QVBoxLayout, 
                             QWidget, QPushButton, QFileDialog, QTextEdit, QHBoxLayout,
                             QMessageBox, QAbstractItemView, QMenu, QLabel, QLineEdit)
from PyQt6.QtCore import Qt, QMimeData, QDataStream, QIODevice, pyqtSignal, QByteArray, QPoint
from PyQt6.QtGui import QDrag, QIcon, QPixmap, QPainter, QColor
import uuid

# 定义MIME类型
MIME_TYPE = "application/x-test-item"


class BreakLoop(Exception):
    """Internal exception to signal breaking out of the nearest enclosing for-loop.

    Carries the number of actions consumed inside the inner block so callers
    can correctly accumulate action counts during step-run.
    """
    def __init__(self, actions=0, runtime_vars=None):
        super().__init__()
        self.actions = actions
        self.runtime_vars = runtime_vars


class StepObject:
    """Represent a step in the sequence. Holds parameters as attributes so each
    dropped item owns its own param state.

    Attributes:
        id: unique id
        module: module name (for functions)
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
        self.outputs = {}


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
            
            # If the item came from the special control category, create a control step
            if module_name == "流程控制":
                item = QListWidgetItem(func_name)
                step = StepObject(type_="control", control=func_name)
            else:
                item = QListWidgetItem(f"{module_name}.{func_name}")
                step = StepObject(type_="function", module=module_name, function=func_name)
            item.setData(Qt.ItemDataRole.UserRole, step)
            item.setData(Qt.ItemDataRole.UserRole + 1, step.id)  # 唯一ID
            self.addItem(item)
            event.acceptProposedAction()
        elif event.mimeData().hasText():
            text = event.mimeData().text()
            if text in ["if", "for", "end", "break"]:
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
        # initialize pass/fail icons
        self.init_status_icons()
        self.load_test_functions()
        self.create_menu_bar()  # 确保方法已定义

    def init_status_icons(self):
        """Create small green/red round icons used to mark PASS/FAIL on steps."""
        def make_icon(color_name):
            size = 16
            pix = QPixmap(size, size)
            try:
                pix.fill(Qt.GlobalColor.transparent)
            except Exception:
                # fallback to white then set mask
                pix.fill(QColor(0, 0, 0, 0))
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            col = QColor(color_name)
            p.setBrush(col)
            p.setPen(QColor(0, 0, 0, 0))
            p.drawEllipse(1, 1, size-3, size-3)
            p.end()
            return QIcon(pix)

        self.icon_pass = make_icon('#2ecc71')  # green
        self.icon_fail = make_icon('#e74c3c')  # red

    def set_item_status(self, item, success: bool):
        """Set the status icon for a QListWidgetItem. Pass True for PASS, False for FAIL.

        If item is None or not a QListWidgetItem, the method is a no-op.
        """
        try:
            if not item:
                return
            if success:
                item.setIcon(self.icon_pass)
            else:
                item.setIcon(self.icon_fail)
        except Exception:
            # non-fatal: do not break execution on icon failures
            pass
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
        # remove extra gaps in left area
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # 函数树
        self.function_tree = DraggableTreeWidget()
        left_layout.addWidget(self.function_tree)

        # 控制语句区域
        self.control_widget = ControlWidget()
        left_layout.addWidget(self.control_widget)

        # 右侧区域（包含序列区和监视器，使用内部水平分割）
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        # remove extra gaps in right area
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 创建序列区域（左）和监视器区域（右）的分割器
        seq_watcher_splitter = QSplitter(Qt.Orientation.Horizontal)
        # make splitter handle less wide to visually remove gap
        try:
            seq_watcher_splitter.setHandleWidth(1)
        except Exception:
            pass

        # --- 序列区域（包含序列列表、控制按钮、步骤设置和输出）
        seq_area = QWidget()
        seq_layout = QVBoxLayout(seq_area)
        # tighten sequence area layout
        seq_layout.setContentsMargins(0, 0, 0, 0)
        seq_layout.setSpacing(0)

        # 控制按钮栏（放在序列的左上角）
        control_bar = QHBoxLayout()
        self.load_button = QPushButton("加载测试函数")
        self.run_button = QPushButton("运行测试序列")
        self.step_button = QPushButton("单步运行")
        self.reset_exec_button = QPushButton("重置执行")
        self.clear_button = QPushButton("清空序列")

        control_bar.addWidget(self.load_button)
        control_bar.addWidget(self.run_button)
        control_bar.addWidget(self.step_button)
        control_bar.addWidget(self.reset_exec_button)
        control_bar.addWidget(self.clear_button)

        seq_layout.addLayout(control_bar)

        # 测试序列列表
        self.sequence_list = DroppableListWidget()
        seq_layout.addWidget(self.sequence_list)

        # --- 步骤设置区域 ---
        self.step_config_group = QWidget()
        step_layout = QVBoxLayout(self.step_config_group)
        step_layout.setContentsMargins(0, 0, 0, 0)

        self.current_param_widgets = {}  # 缓存当前参数控件

        step_layout.addWidget(QLabel("<b>步骤设置</b>"))

        # 输入参数区
        self.input_params_layout = QVBoxLayout()
        # remove spacing between input rows
        self.input_params_layout.setSpacing(0)
        self.input_params_layout.setContentsMargins(0, 0, 0, 0)
        self.input_params_widget = QWidget()
        self.input_params_widget.setLayout(self.input_params_layout)
        step_layout.addWidget(QLabel("输入参数:"))
        step_layout.addWidget(self.input_params_widget)

        # 输出参数区
        self.output_params_label = QLabel("-")
        self.output_params_label.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 5px; border: 1px solid #ccc; }")
        step_layout.addWidget(QLabel("输出参数:"))
        step_layout.addWidget(self.output_params_label)

        seq_layout.addWidget(self.step_config_group)

        # 输出区域
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        seq_layout.addWidget(self.output_text)

        seq_watcher_splitter.addWidget(seq_area)

        # --- 监视器区域（右侧） ---
        watcher_widget = QWidget()
        watcher_layout = QVBoxLayout(watcher_widget)
        watcher_layout.setContentsMargins(0, 0, 0, 0)
        watcher_layout.addWidget(QLabel("变量监视器"))
        from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
        self.watcher_tree = QTreeWidget()
        self.watcher_tree.setHeaderLabel("变量")
        watcher_layout.addWidget(self.watcher_tree)

        seq_watcher_splitter.addWidget(watcher_widget)

        # 调整默认大小比例
        seq_watcher_splitter.setSizes([700, 300])

        right_layout.addWidget(seq_watcher_splitter)
        
        # 添加到分割器
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)
        # reduce splitter handle width and initial sizes to avoid large gap
        try:
            main_splitter.setHandleWidth(1)
        except Exception:
            pass
        main_splitter.setSizes([300, 700])
        
        # 连接信号
        self.load_button.clicked.connect(self.load_test_functions)
        self.run_button.clicked.connect(self.run_sequence)
        self.step_button.clicked.connect(self.step_run)
        self.reset_exec_button.clicked.connect(self.reset_executor)
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
            # control item: show appropriate param inputs
            if isinstance(data, StepObject):
                control_type = data.control
            else:
                control_type = data.get("control")

            if control_type == "if":
                # condition expression, can reference other steps via ${#N:key} or loop vars via ${@var}
                cond = data.params.get("condition", "") if isinstance(data, StepObject) else self.step_params_cache.get(item_id, {}).get("condition", "")
                edit = self.add_input_row("condition", cond)
                if isinstance(data, StepObject):
                    edit.textChanged.connect(lambda val, it=current: self.on_param_changed(it, "condition", val))
            elif control_type == "for":
                iterable = data.params.get("iterable", "") if isinstance(data, StepObject) else self.step_params_cache.get(item_id, {}).get("iterable", "")
                varname = data.params.get("var", "_loop") if isinstance(data, StepObject) else self.step_params_cache.get(item_id, {}).get("var", "_loop")
                edit1 = self.add_input_row("iterable", iterable)
                edit2 = self.add_input_row("var", varname)
                if isinstance(data, StepObject):
                    edit1.textChanged.connect(lambda val, it=current: self.on_param_changed(it, "iterable", val))
                    edit2.textChanged.connect(lambda val, it=current: self.on_param_changed(it, "var", val))
            else:
                # end or unknown control
                self.output_params_label.setText("-")

    def load_test_functions(self):
        """加载当前目录下的测试函数"""
        self.function_tree.clear()
        self.test_functions = {}
        # reset parsed return names
        self.func_return_names = {}
        
        # 查找 Testcase/ 目录（优先），否则回退到当前目录
        base_dir = os.path.join(os.getcwd(), 'Testcase') if os.path.isdir(os.path.join(os.getcwd(), 'Testcase')) else os.getcwd()
        for fname in os.listdir(base_dir):
            if fname.endswith('.py') and fname.startswith('test_') and fname != 'test_functions.py':
                file_path = os.path.join(base_dir, fname)
                module_name = os.path.splitext(os.path.basename(file_path))[0]
                try:
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    # attempt to parse source to find return variable names or dict keys
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            src = f.read()
                        import ast
                        tree = ast.parse(src)
                        func_returns = {}
                        for node in tree.body:
                            if isinstance(node, ast.FunctionDef):
                                ret_names = []
                                for st in ast.walk(node):
                                    if isinstance(st, ast.Return) and st.value is not None:
                                        v = st.value
                                        # return of a simple name: return sum
                                        if isinstance(v, ast.Name):
                                            ret_names.append(v.id)
                                        # return of a dict literal: return {'k': val}
                                        elif isinstance(v, ast.Dict):
                                            for key in v.keys:
                                                if isinstance(key, ast.Constant):
                                                    ret_names.append(str(key.value))
                                if ret_names:
                                    func_returns[node.name] = list(dict.fromkeys(ret_names))
                        if func_returns:
                            self.func_return_names[module_name] = func_returns
                    except Exception:
                        # ignore parsing errors
                        pass

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

        # 添加流程控制分类（可拖拽到序列中作为控制节点）
        control_item = QTreeWidgetItem(["流程控制"])
        for ctrl in ["if", "for", "end", "break"]:
            child = QTreeWidgetItem([ctrl])
            control_item.addChild(child)
        self.function_tree.addTopLevelItem(control_item)
        self.function_tree.expandItem(control_item)
        
    def clear_sequence(self):
        """清空测试序列"""
        # first clear stored params/outputs on each step object
        for i in range(self.sequence_list.count()):
            it = self.sequence_list.item(i)
            data = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, StepObject):
                data.params.clear()
                data.outputs.clear()

        # clear the visual list and caches
        self.sequence_list.clear()
        self.step_params_cache.clear()
        # reset execution state and clear any markers
        self.exec_state = None
        try:
            self.mark_exec_index(None)
        except Exception:
            pass

        # clear watcher and output
        self.update_output()
        self.update_watcher({})
        self.output_text.clear()
        
    def update_output(self):
        """更新输出显示"""
        sequence_text = "当前测试序列:\n"
        for i in range(self.sequence_list.count()):
            item = self.sequence_list.item(i)
            # item.text() may include an exec marker; strip any marker suffix before building the output
            base = item.text().split('  ')[0]
            sequence_text += f"{i+1}. {base}\n"
        self.output_text.setText(sequence_text)
        # refresh visible numbering and exec marker
        try:
            idx = None
            if hasattr(self, 'exec_state') and self.exec_state is not None:
                idx = self.exec_state.get('index')
            self.mark_exec_index(idx)
        except Exception:
            try:
                self.mark_exec_index(None)
            except Exception:
                pass

    # Executor helpers and state for step execution
    def _safe_eval(self, expr, local_vars=None):
        if local_vars is None:
            local_vars = {}
        try:
            import ast
            return ast.literal_eval(expr)
        except Exception:
            try:
                safe_globals = {"__builtins__": None, 'True': True, 'False': False, 'None': None}
                return eval(expr, safe_globals, local_vars)
            except Exception:
                return False

    def _run_block(self, start_idx, end_idx, runtime_vars, max_actions=None):
        """Execute items from start_idx..end_idx. If max_actions is set, stop after that many actions (control evaluations or function calls).

        Returns (new_index, runtime_vars, actions_done)
        """
        actions = 0
        i = start_idx
        while i <= end_idx:
            item = self.sequence_list.item(i)
            step_data = item.data(Qt.ItemDataRole.UserRole)

            # Determine control or function
            if isinstance(step_data, StepObject):
                if step_data.type == 'control':
                    ctrl = step_data.control
                else:
                    ctrl = None
            else:
                ctrl = step_data.get('control') if isinstance(step_data, dict) else None

            if ctrl == 'if':
                match = self.find_matching_end(i)
                cond_raw = step_data.params.get('condition', '') if isinstance(step_data, StepObject) else self.step_params_cache.get(item.data(Qt.ItemDataRole.UserRole + 1), {}).get('condition', '')
                cond_val = self.resolve_references(cond_raw, runtime_vars)
                cond_bool = cond_val if isinstance(cond_val, bool) else self._safe_eval(str(cond_val), runtime_vars)
                self.output_text.append(f"IF condition ({cond_raw}) -> {cond_bool}")
                self.update_watcher(runtime_vars)
                actions += 1
                if max_actions is not None and actions >= max_actions:
                    return (i+1, runtime_vars, actions)
                if cond_bool:
                    if match != -1 and match > i:
                        ni, nv, a = self._run_block(i+1, match-1, runtime_vars, None if max_actions is None else (max_actions - actions))
                        actions += a
                        runtime_vars = nv
                        i = match + 1
                        if max_actions is not None and actions >= max_actions:
                            return (i, runtime_vars, actions)
                        continue
                    else:
                        i += 1
                        continue
                else:
                    i = match + 1 if match != -1 else i + 1
                    continue
            elif ctrl == 'for':
                match = self.find_matching_end(i)
                iterable_raw = step_data.params.get('iterable', '') if isinstance(step_data, StepObject) else self.step_params_cache.get(item.data(Qt.ItemDataRole.UserRole + 1), {}).get('iterable', '')
                varname = step_data.params.get('var', '_loop') if isinstance(step_data, StepObject) else self.step_params_cache.get(item.data(Qt.ItemDataRole.UserRole + 1), {}).get('var', '_loop')
                iterable_val = self.resolve_references(iterable_raw, runtime_vars)
                if isinstance(iterable_val, int):
                    iterator = range(iterable_val)
                elif isinstance(iterable_val, (list, tuple)):
                    iterator = iterable_val
                else:
                    try:
                        iterator = list(self._safe_eval(str(iterable_val), runtime_vars))
                    except Exception:
                        iterator = []

                self.output_text.append(f"FOR over {iterable_raw} -> {list(iterator)}")
                self.update_watcher(runtime_vars)
                actions += 1
                if max_actions is not None and actions >= max_actions:
                    return (i+1, runtime_vars, actions)
                if match != -1 and match > i:
                    for val in iterator:
                        new_vars = dict(runtime_vars)
                        new_vars[varname] = val
                        try:
                            ni, nv, a = self._run_block(i+1, match-1, new_vars, None if max_actions is None else (max_actions - actions))
                            actions += a
                        except BreakLoop as ex:
                            # inner block requested a break: consume its reported actions and stop iterating
                            actions += ex.actions
                            runtime_vars = ex.runtime_vars or runtime_vars
                            # if we've hit the max actions for a step-run, resume after the for-block
                            if max_actions is not None and actions >= max_actions:
                                return (match+1, runtime_vars, actions)
                            break
                    i = match + 1
                    continue
                else:
                    i += 1
                    continue
            elif ctrl == 'break':
                # signal to the enclosing for-loop to stop
                actions += 1
                self.output_text.append("BREAK")
                self.update_watcher(runtime_vars)
                # raise to inform the caller (the parent for-handler) to stop iterating
                raise BreakLoop(actions=1, runtime_vars=runtime_vars)
            elif ctrl == 'end':
                i += 1
                continue

            # function step
            if isinstance(step_data, StepObject):
                if step_data.type == 'function':
                    module_name = step_data.module
                    func_name = step_data.function
                    func = self.test_functions.get(module_name, {}).get(func_name)
                else:
                    func = None
            else:
                if isinstance(step_data, dict) and step_data.get('type') == 'function':
                    module_name = step_data.get('module')
                    func_name = step_data.get('function')
                    func = self.test_functions.get(module_name, {}).get(func_name)
                else:
                    func = None

            if func is None:
                self.output_text.append(f"跳过未知步骤或控制: {item.text()}")
                self.update_watcher(runtime_vars)
                i += 1
                continue

            self.output_text.append(f"执行: {module_name}.{func_name}...")
            self.update_watcher(runtime_vars)

            import inspect
            sig = inspect.signature(func)
            params = sig.parameters
            args = {}

            for param_name in params.keys():
                if isinstance(step_data, StepObject):
                    raw = step_data.params.get(param_name, '')
                else:
                    raw = self.step_params_cache.get(item.data(Qt.ItemDataRole.UserRole + 1), {}).get(param_name, '')
                resolved = self.resolve_references(raw, runtime_vars)
                param_type = params[param_name].annotation
                if param_type != inspect.Parameter.empty:
                    try:
                        if param_type == bool:
                            value = bool(resolved) if isinstance(resolved, bool) else str(resolved).lower() in ('true', '1', 'yes', 'on')
                        elif param_type in (int, float):
                            value = param_type(resolved)
                        else:
                            value = resolved
                    except Exception as e:
                        self.output_text.append(f"参数 '{param_name}' 类型转换失败: {e}")
                        value = resolved
                else:
                    value = resolved
                args[param_name] = value

            try:
                result = func(**args)
                if isinstance(step_data, StepObject):
                    if isinstance(result, dict):
                        step_data.outputs.update(result)
                    else:
                        # store generic return and also map to any param name whose passed value equals the return
                        step_data.outputs['return'] = result
                        try:
                            for pn, pv in args.items():
                                # simple equality check to map common pattern where function returns an input value
                                if pv == result:
                                    step_data.outputs[pn] = result
                                # also map any predicted return names (parsed from source) to the returned value
                                preds = self.func_return_names.get(step_data.module, {}).get(step_data.function, [])
                                for pred in preds:
                                    if pred not in step_data.outputs:
                                        step_data.outputs[pred] = result
                        except Exception:
                            # don't break execution on mapping issues
                            pass
                # determine success: None or truthy -> success
                success = (result is None) or bool(result)
                self.output_text.append(f"{'成功' if success else '失败'}")
                try:
                    self.set_item_status(item, success)
                except Exception:
                    pass
            except Exception as e:
                self.output_text.append(f"错误: {str(e)}")
                try:
                    self.set_item_status(item, False)
                except Exception:
                    pass

            self.update_watcher(runtime_vars)
            actions += 1
            if max_actions is not None and actions >= max_actions:
                return (i+1, runtime_vars, actions)
            i += 1

        return (i, runtime_vars, actions)

    def step_run(self):
        """Execute a single action (control evaluation or a function call)."""
        if not hasattr(self, 'exec_state') or self.exec_state is None:
            # initialize execution state with a loop stack for single-stepping through for-loops
            self.exec_state = {'index': 0, 'vars': {}, 'loop_stack': []}
        start = self.exec_state['index']
        end = self.sequence_list.count() - 1
        if start > end:
            self.output_text.append("已到序列末尾；请重置执行以重新开始。")
            return
        # show marker at current position before executing
        self.mark_exec_index(start)
        # Helper: locate innermost loop that contains index 'start'
        def find_enclosing_loop(start_idx):
            ls = self.exec_state.get('loop_stack', [])
            for entry in reversed(ls):
                if entry['start'] < start_idx <= entry['end']:
                    return entry
            return None

        item = self.sequence_list.item(start)
        step_data = item.data(Qt.ItemDataRole.UserRole)

        # If the current item is a for-header and we're not already inside that for-loop,
        # initialize loop state and set the first loop variable value so the next step
        # will execute the inner block with the loop var present.
        if isinstance(step_data, StepObject) and step_data.type == 'control' and step_data.control == 'for':
            # avoid double-initializing if we already have a loop stack entry for this start
            existing = None
            for e in self.exec_state.get('loop_stack', []):
                if e['start'] == start:
                    existing = e
                    break

            match = self.find_matching_end(start)
            iterable_raw = step_data.params.get('iterable', '')
            varname = step_data.params.get('var', '_loop')
            iterable_val = self.resolve_references(iterable_raw, dict(self.exec_state['vars']))
            # normalize iterable same as full-run/_run_block
            if isinstance(iterable_val, int):
                iterator = list(range(iterable_val))
            elif isinstance(iterable_val, (list, tuple)):
                iterator = list(iterable_val)
            else:
                try:
                    iterator = list(self._safe_eval(str(iterable_val), dict(self.exec_state['vars'])))
                except Exception:
                    iterator = []

            # consume the 'for' header as this step
            if not iterator:
                # empty iterator: skip the whole for-block
                ni = match + 1 if match != -1 else start + 1
                self.exec_state['index'] = ni
                self.output_text.append(f"单步执行: 空迭代对象，跳过 for-block，下一索引 {ni}")
                if self.exec_state['index'] <= end:
                    self.mark_exec_index(self.exec_state['index'])
                else:
                    self.mark_exec_index(None)
                return

            # initialize loop stack entry
            if existing is None:
                entry = {'start': start, 'end': match, 'iterator': iterator, 'pos': 0, 'var': varname}
                self.exec_state.setdefault('loop_stack', []).append(entry)
            else:
                entry = existing

            # set loop var to first element and move to first inner index
            new_vars = dict(self.exec_state['vars'])
            new_vars[varname] = entry['iterator'][entry['pos']]
            self.exec_state['vars'] = new_vars
            self.exec_state['index'] = start + 1 if match != -1 else start + 1
            # update UI
            self.mark_exec_index(self.exec_state['index'])
            self.output_text.append(f"进入 for: 设 {varname} = {entry['iterator'][entry['pos']]}，下一索引 {self.exec_state['index']}")
            return

        # If we're inside a loop body, run one action within that loop and handle iteration bookkeeping
        enclosing = find_enclosing_loop(start)
        if enclosing is not None:
            try:
                ni, nv, a = self._run_block(start, enclosing['end'], dict(self.exec_state['vars']), max_actions=1)
            except BreakLoop as ex:
                # break breaks out of this enclosing loop: remove this loop entry and resume after it
                # consume the break's runtime_vars if provided
                try:
                    self.exec_state['vars'] = ex.runtime_vars or dict(self.exec_state['vars'])
                except Exception:
                    pass
                # pop the loop entry
                try:
                    self.exec_state['loop_stack'].remove(enclosing)
                except Exception:
                    pass
                ni = enclosing['end'] + 1
                self.exec_state['index'] = ni
                # update marker/UI
                if self.exec_state['index'] <= end:
                    self.mark_exec_index(self.exec_state['index'])
                else:
                    self.mark_exec_index(None)
                self.output_text.append(f"在循环内遇到 break，跳至索引 {ni}")
                return

            # update runtime vars
            self.exec_state['vars'] = nv

            # if inner block finished (ni passed the end), advance iterator
            if ni > enclosing['end']:
                enclosing['pos'] += 1
                if enclosing['pos'] < len(enclosing['iterator']):
                    # set next loop var and point back to first inner item
                    self.exec_state['vars'][enclosing['var']] = enclosing['iterator'][enclosing['pos']]
                    self.exec_state['index'] = enclosing['start'] + 1
                    self.mark_exec_index(self.exec_state['index'])
                    self.output_text.append(f"循环下次迭代: 设 {enclosing['var']} = {enclosing['iterator'][enclosing['pos']]}，下一索引 {self.exec_state['index']}")
                    return
                else:
                    # loop fully completed: pop and resume after end
                    try:
                        self.exec_state['loop_stack'].remove(enclosing)
                    except Exception:
                        pass
                    self.exec_state['index'] = enclosing['end'] + 1
                    if self.exec_state['index'] <= end:
                        self.mark_exec_index(self.exec_state['index'])
                    else:
                        self.mark_exec_index(None)
                    self.output_text.append(f"循环完成，下一索引 {self.exec_state['index']}")
                    return
            else:
                # still inside inner block; resume at returned index
                self.exec_state['index'] = ni
                if self.exec_state['index'] <= end:
                    self.mark_exec_index(self.exec_state['index'])
                else:
                    self.mark_exec_index(None)
                self.output_text.append(f"单步执行: 完成 {a} 个操作，下一索引 {ni}")
                return

        # default: not a for header nor inside a loop - just execute one action normally
        try:
            ni, nv, a = self._run_block(start, end, dict(self.exec_state['vars']), max_actions=1)
        except BreakLoop as ex:
            # break encountered with no enclosing for-block in this call chain;
            # treat it as one consumed action and advance past the current index
            ni = start + 1
            nv = ex.runtime_vars or dict(self.exec_state['vars'])
            a = ex.actions
        else:
            nv = nv
        self.exec_state['index'] = ni
        self.exec_state['vars'] = nv
        # update marker to new position (or clear if finished)
        if self.exec_state['index'] <= end:
            self.mark_exec_index(self.exec_state['index'])
        else:
            self.mark_exec_index(None)
        self.output_text.append(f"单步执行: 完成 {a} 个操作，下一索引 {ni}")

    def reset_executor(self):
        """Reset execution state and clear runtime variables and per-step outputs.

        This clears:
          - self.exec_state (index and runtime vars)
          - per-step outputs stored in StepObject.outputs
          - any global_vars stored on the window
        It does NOT clear step parameter values (用户输入的参数仍保留)。
        """
        # reset exec state (include loop_stack for single-step loop handling)
        self.exec_state = {'index': 0, 'vars': {}, 'loop_stack': []}

        # clear outputs collected on each step so watcher no longer shows previous run values
        for i in range(self.sequence_list.count()):
            it = self.sequence_list.item(i)
            data = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, StepObject):
                try:
                    data.outputs.clear()
                    # clear any status icon
                    try:
                        it.setIcon(QIcon())
                    except Exception:
                        pass
                except Exception:
                    pass

        # clear global runtime variables if present
        try:
            self.global_vars = {}
        except Exception:
            pass

        # refresh watcher and execution marker
        self.update_watcher({})
        self.mark_exec_index(self.exec_state['index'])
        self.output_text.append("执行状态已重置；已清除运行时变量与步骤输出")

    def update_watcher(self, runtime_vars):
        """Refresh the watcher tree showing variables organized by sequence steps."""
        self.watcher_tree.clear()
        
        # Show variables organized by sequence steps
        for i in range(self.sequence_list.count()):
            it = self.sequence_list.item(i)
            data = it.data(Qt.ItemDataRole.UserRole)
            
            if not isinstance(data, StepObject):
                continue
                
            # Create a top-level node for this step
            step_node = QTreeWidgetItem([f"步骤 {i+1}: {it.text()}"])
            
            if data.type == 'function':
                # Function steps show both inputs and outputs
                inputs_node = QTreeWidgetItem(["输入参数"])
                for k, v in data.params.items():
                    inputs_node.addChild(QTreeWidgetItem([f"{k}: {v}"]))
                step_node.addChild(inputs_node)
                
                outputs_node = QTreeWidgetItem(["输出结果"])
                for k, v in data.outputs.items():
                    outputs_node.addChild(QTreeWidgetItem([f"{k}: {v}"]))
                step_node.addChild(outputs_node)
                
            elif data.type == 'control':
                # Control steps show their specific parameters
                if data.control == 'if':
                    ctrl_node = QTreeWidgetItem(["条件"])
                    condition = data.params.get('condition', '')
                    ctrl_node.addChild(QTreeWidgetItem([f"表达式: {condition}"]))
                    step_node.addChild(ctrl_node)
                    
                elif data.control == 'for':
                    ctrl_node = QTreeWidgetItem(["循环"])
                    iterable = data.params.get('iterable', '')
                    varname = data.params.get('var', '_loop')
                    ctrl_node.addChild(QTreeWidgetItem([f"迭代对象: {iterable}"]))
                    ctrl_node.addChild(QTreeWidgetItem([f"循环变量: {varname}"]))
                    step_node.addChild(ctrl_node)
                    
            self.watcher_tree.addTopLevelItem(step_node)

        # Runtime Variables (e.g., loop variables)
        if runtime_vars:
            runtime_node = QTreeWidgetItem(["运行时变量"])
            for k, v in runtime_vars.items():
                runtime_node.addChild(QTreeWidgetItem([f"{k}: {v}"]))
            self.watcher_tree.addTopLevelItem(runtime_node)
            
        # Global Variables
        gvars = getattr(self, 'global_vars', {})
        if gvars:
            globals_node = QTreeWidgetItem(["全局变量"])
            for k, v in gvars.items():
                globals_node.addChild(QTreeWidgetItem([f"{k}: {v}"]))
            self.watcher_tree.addTopLevelItem(globals_node)
        
    def mark_exec_index(self, idx):
        """Visually mark the execution index in the sequence list by appending an arrow to the item's text.

        Args:
            idx (int|None): index to mark, or None to clear all markers.
        """
        # Rebuild each item's displayed text to include a leading index and an optional exec marker.
        for i in range(self.sequence_list.count()):
            item = self.sequence_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            # compute base label from StepObject when possible to avoid accumulating arrows
            if isinstance(data, StepObject):
                if data.type == 'function':
                    base = f"{data.module}.{data.function}"
                else:
                    base = data.control
            else:
                # fallback: strip any previous arrow suffix
                base = item.text().split('  ')[0]

            display = f"{i+1}. {base}"
            if idx is not None and i == idx:
                display = f"{display}  <-"
            item.setText(display)
        
    def run_sequence(self):
        """运行测试序列"""
        output = "开始执行测试序列...\n"
        self.output_text.setText(output)
        QApplication.processEvents()  # 更新界面

        def safe_eval(expr, local_vars=None):
            if local_vars is None:
                local_vars = {}
            try:
                import ast
                return ast.literal_eval(expr)
            except Exception:
                try:
                    safe_globals = {"__builtins__": None, 'True': True, 'False': False, 'None': None}
                    return eval(expr, safe_globals, local_vars)
                except Exception:
                    return False

        def run_block(start_idx, end_idx, runtime_vars):
            """Execute items from start_idx to end_idx inclusive using runtime_vars for ${@var} replacements."""
            nonlocal output
            # update watcher at the start of block
            try:
                self.update_watcher(runtime_vars)
            except Exception:
                pass
            i = start_idx
            while i <= end_idx:
                item = self.sequence_list.item(i)
                step_data = item.data(Qt.ItemDataRole.UserRole)

                # Determine control or function
                if isinstance(step_data, StepObject):
                    if step_data.type == 'control':
                        ctrl = step_data.control
                    else:
                        ctrl = None
                else:
                    ctrl = step_data.get('control') if isinstance(step_data, dict) else None

                if ctrl == 'if':
                    # find matching end
                    match = self.find_matching_end(i)
                    cond_raw = step_data.params.get('condition', '') if isinstance(step_data, StepObject) else self.step_params_cache.get(item.data(Qt.ItemDataRole.UserRole + 1), {}).get('condition', '')
                    cond_val = self.resolve_references(cond_raw, runtime_vars)
                    # evaluate boolean
                    cond_bool = cond_val if isinstance(cond_val, bool) else safe_eval(str(cond_val), runtime_vars)
                    output += f"IF condition ({cond_raw}) -> {cond_bool}\n"
                    self.output_text.setText(output)
                    # update watcher after evaluating condition
                    try:
                        self.update_watcher(runtime_vars)
                    except Exception:
                        pass
                    QApplication.processEvents()
                    if cond_bool:
                        # execute block inside
                        if match != -1 and match > i:
                            run_block(i+1, match-1, runtime_vars)
                            i = match + 1
                            continue
                        else:
                            i += 1
                            continue
                    else:
                        # skip to end
                        i = match + 1 if match != -1 else i + 1
                        continue
                elif ctrl == 'for':
                    match = self.find_matching_end(i)
                    iterable_raw = step_data.params.get('iterable', '') if isinstance(step_data, StepObject) else self.step_params_cache.get(item.data(Qt.ItemDataRole.UserRole + 1), {}).get('iterable', '')
                    varname = step_data.params.get('var', '_loop') if isinstance(step_data, StepObject) else self.step_params_cache.get(item.data(Qt.ItemDataRole.UserRole + 1), {}).get('var', '_loop')
                    iterable_val = self.resolve_references(iterable_raw, runtime_vars)
                    # normalize iterable
                    if isinstance(iterable_val, int):
                        iterator = range(iterable_val)
                    elif isinstance(iterable_val, (list, tuple)):
                        iterator = iterable_val
                    else:
                        # try to eval as python expression
                        try:
                            iterator = list(safe_eval(str(iterable_val), runtime_vars))
                        except Exception:
                            iterator = []

                    output += f"FOR over {iterable_raw} -> {list(iterator)}\n"
                    self.output_text.setText(output)
                    # update watcher after preparing iterator
                    try:
                        self.update_watcher(runtime_vars)
                    except Exception:
                        pass
                    QApplication.processEvents()
                    if match != -1 and match > i:
                        for val in iterator:
                            new_vars = dict(runtime_vars)
                            new_vars[varname] = val
                            try:
                                run_block(i+1, match-1, new_vars)
                            except BreakLoop:
                                # break out of the iterator loop and continue after the matching end
                                break
                        i = match + 1
                        continue
                    else:
                        i += 1
                        continue
                elif ctrl == 'break':
                    # break encountered during full run: stop the innermost for loop
                    output += "BREAK\n"
                    self.output_text.setText(output)
                    try:
                        self.update_watcher(runtime_vars)
                    except Exception:
                        pass
                    QApplication.processEvents()
                    # raise to inform caller to break the iterator
                    raise BreakLoop(actions=1, runtime_vars=runtime_vars)
                elif ctrl == 'end':
                    # should be handled by find_matching_end logic; just advance
                    i += 1
                    continue

                # else, it's a function step
                # prepare and call function
                if isinstance(step_data, StepObject):
                    if step_data.type == 'function':
                        module_name = step_data.module
                        func_name = step_data.function
                        func = self.test_functions.get(module_name, {}).get(func_name)
                    else:
                        func = None
                else:
                    if isinstance(step_data, dict) and step_data.get('type') == 'function':
                        module_name = step_data.get('module')
                        func_name = step_data.get('function')
                        func = self.test_functions.get(module_name, {}).get(func_name)
                    else:
                        func = None

                if func is None:
                    output += f"跳过未知步骤或控制: {item.text()}\n"
                    self.output_text.setText(output)
                    try:
                        self.update_watcher(runtime_vars)
                    except Exception:
                        pass
                    QApplication.processEvents()
                    i += 1
                    continue

                output += f"执行: {module_name}.{func_name}... "
                self.output_text.setText(output)
                QApplication.processEvents()

                import inspect
                sig = inspect.signature(func)
                params = sig.parameters
                args = {}

                for param_name in params.keys():
                    # get raw value string from step params or current widgets
                    if isinstance(step_data, StepObject):
                        raw = step_data.params.get(param_name, '')
                    else:
                        raw = self.step_params_cache.get(item.data(Qt.ItemDataRole.UserRole + 1), {}).get(param_name, '')

                    # resolve references
                    resolved = self.resolve_references(raw, runtime_vars)

                    # type conversion
                    param_type = params[param_name].annotation
                    if param_type != inspect.Parameter.empty:
                        try:
                            if param_type == bool:
                                value = bool(resolved) if isinstance(resolved, bool) else str(resolved).lower() in ('true', '1', 'yes', 'on')
                            elif param_type in (int, float):
                                value = param_type(resolved)
                            else:
                                value = resolved
                        except Exception as e:
                            output += f"参数 '{param_name}' 类型转换失败: {e}\n"
                            self.output_text.setText(output)
                            QApplication.processEvents()
                            value = resolved
                    else:
                        value = resolved
                    args[param_name] = value

                try:
                    result = func(**args)
                    # store outputs
                    if isinstance(step_data, StepObject):
                        if isinstance(result, dict):
                            step_data.outputs.update(result)
                        else:
                            step_data.outputs['return'] = result
                            try:
                                for pn, pv in args.items():
                                    if pv == result:
                                        step_data.outputs[pn] = result
                                # also map any predicted return names (parsed from source) to the returned value
                                preds = self.func_return_names.get(module_name, {}).get(func_name, [])
                                for pred in preds:
                                    if pred not in step_data.outputs:
                                        step_data.outputs[pred] = result
                            except Exception:
                                pass
                    # determine success and set icon
                    success = (result is None) or bool(result)
                    output += f"{'成功' if success else '失败'}\n"
                    try:
                        self.set_item_status(item, success)
                    except Exception:
                        pass
                except Exception as e:
                    output += f"错误: {str(e)}\n"
                    try:
                        self.set_item_status(item, False)
                    except Exception:
                        pass

                self.output_text.setText(output)
                # update watcher after executing a function step
                try:
                    self.update_watcher(runtime_vars)
                except Exception:
                    pass
                QApplication.processEvents()
                i += 1

        try:
            run_block(0, self.sequence_list.count()-1, {})
            output += "测试序列执行完成。\n"
            self.output_text.setText(output)
        except BreakLoop:
            # break outside of any for-block: ignore and finish run
            output += "遇到 break（未在循环内），已忽略。\n"
            self.output_text.setText(output)
        except Exception as e:
            output += f"执行过程中发生错误: {str(e)}\n"
            self.output_text.setText(output)

    def add_input_row(self, param_name, default_value="", read_only=False):
        """添加一行参数输入，并输出调试信息"""
        print(f"[DEBUG] 创建输入框: {param_name} = '{default_value}'")
        row_layout = QHBoxLayout()
        # remove spacing/margins so input rows sit flush together
        row_layout.setSpacing(0)
        row_layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(f"{param_name}:")
        label.setFixedWidth(100)
        edit = QLineEdit(str(default_value))
        edit.setReadOnly(read_only)
        row_layout.addWidget(label)
        row_layout.addWidget(edit)

        # reference insert button: opens a menu of previous steps/outputs to insert ${#N:key}
        ref_btn = QPushButton("引用")
        ref_btn.setToolTip("插入对前一步骤输出/参数的引用")
        ref_btn.setFixedWidth(48)
        row_layout.addWidget(ref_btn)
        self.input_params_layout.addLayout(row_layout)
        self.current_param_widgets[param_name] = edit
        print(f"[DEBUG] QLineEdit.text() after set: '{edit.text()}'")
        edit.repaint()
        edit.update()
        # build and show the menu when ref_btn is clicked
        def show_ref_menu():
            """Show a flat reference menu listing each available step/key with the step index
            so duplicate functions are unambiguous.
            """
            menu = QMenu(self)
            has_any = False
            # gather steps and add actions directly so each action clearly shows the step index
            for i in range(self.sequence_list.count()):
                it = self.sequence_list.item(i)
                data = it.data(Qt.ItemDataRole.UserRole)
                if not isinstance(data, StepObject):
                    continue
                title = it.text()
                # collect candidate keys: outputs (prefer) then params
                keys = []
                for k in data.outputs.keys():
                    keys.append((k, 'out'))
                for k in data.params.keys():
                    if k not in data.outputs:
                        keys.append((k, 'param'))
                if data.type == 'function':
                    preds = self.func_return_names.get(data.module, {}).get(data.function, [])
                    for k in preds:
                        if not any(k == ex for ex, _ in keys):
                            keys.append((k, 'pred'))

                if not keys:
                    continue

                for key, kind in keys:
                    # label includes step index and function/control title to avoid ambiguity
                    suffix = ''
                    if kind == 'out' or kind == 'pred':
                        suffix = ' (out)'
                    action_text = f"#{i+1} {title} :: {key}{suffix}"
                    act = menu.addAction(action_text)
                    if kind == 'pred':
                        act.setToolTip('预测输出（未运行）：运行后会填充真实值')
                    def make_handler(step_index, k):
                        return lambda checked=False: edit.insert(f"${{{'#'}{step_index}:{k}}}")
                    act.triggered.connect(make_handler(i+1, key))
                    has_any = True

            if not has_any:
                a = menu.addAction("无可用引用")
                a.setEnabled(False)

            menu.exec(ref_btn.mapToGlobal(ref_btn.rect().bottomLeft()))

        ref_btn.clicked.connect(show_ref_menu)

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

    def resolve_references(self, text, runtime_vars=None):
        """Resolve reference patterns in text.

        Supported patterns:
          ${#N:key}   -> value of step N (1-based) output 'key' or param 'key'
          ${@var}     -> runtime var (e.g., loop var)

        If text isn't a string with references, return it unchanged.
        """
        if runtime_vars is None:
            runtime_vars = {}

        if not isinstance(text, str):
            return text

        import re

        def repl_step(m):
            idx = int(m.group(1)) - 1
            key = m.group(2)
            if 0 <= idx < self.sequence_list.count():
                item = self.sequence_list.item(idx)
                data = item.data(Qt.ItemDataRole.UserRole)
                # prefer outputs then params
                if isinstance(data, StepObject):
                    if key in data.outputs:
                        return str(data.outputs.get(key))
                    return str(data.params.get(key, ""))
                else:
                    cache = self.step_params_cache.get(item.data(Qt.ItemDataRole.UserRole + 1), {})
                    return str(cache.get(key, ""))
            return ""

        def repl_var(m):
            name = m.group(1)
            return str(runtime_vars.get(name, ""))

        # replace ${#N:key}
        text2 = re.sub(r"\$\{#(\d+):([^}]+)\}", repl_step, text)
        # replace ${@var}
        text3 = re.sub(r"\$\{@([^}]+)\}", repl_var, text2)

        # Try to interpret as literal (number, list) if possible
        try:
            import ast
            val = ast.literal_eval(text3)
            return val
        except Exception:
            pass

        return text3

    def find_matching_end(self, start_index):
        """Find the matching 'end' index for a control starting at start_index.

        Accounts for nested controls.
        Returns index of the matching end, or -1 if not found.
        """
        depth = 0
        for i in range(start_index, self.sequence_list.count()):
            item = self.sequence_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            ctrl = None
            if isinstance(data, StepObject) and data.type == "control":
                ctrl = data.control
            elif isinstance(data, dict) and data.get("type") == "control":
                ctrl = data.get("control")

            if ctrl in ("if", "for"):
                depth += 1
            elif ctrl == "end":
                depth -= 1
                if depth == 0:
                    return i
        return -1

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()