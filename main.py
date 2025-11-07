import sys
import os
import importlib.util
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem, 
                             QListWidget, QListWidgetItem, QSplitter, QVBoxLayout, 
                             QWidget, QPushButton, QFileDialog, QTextEdit, QHBoxLayout,
                             QMessageBox, QAbstractItemView, QMenu)
from PyQt6.QtCore import Qt, QMimeData, QDataStream, QIODevice, pyqtSignal, QByteArray, QPoint
from PyQt6.QtGui import QDrag, QIcon

# 定义MIME类型
MIME_TYPE = "application/x-test-item"

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
            item.setData(Qt.ItemDataRole.UserRole, {"type": "function", "module": module_name, "function": func_name})
            self.addItem(item)
            event.acceptProposedAction()
        elif event.mimeData().hasText():
            text = event.mimeData().text()
            if text in ["if", "for", "end"]:
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, {"type": "control", "control": text})
                self.addItem(item)
                event.acceptProposedAction()
        else:
            super().dropEvent(event)
        self.itemMoved.emit()

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
        self.init_ui()
        self.load_test_functions()
        
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
                data = item.data(Qt.ItemDataRole.UserRole)
                
                if data["type"] == "function":
                    module_name = data["module"]
                    func_name = data["function"]
                    
                    output += f"执行: {module_name}.{func_name}... "
                    self.output_text.setText(output)
                    QApplication.processEvents()
                    
                    # 调用函数
                    if module_name in self.test_functions and func_name in self.test_functions[module_name]:
                        try:
                            result = self.test_functions[module_name][func_name]()
                            output += f"{'成功' if result is None or result else '失败'}\n"
                        except Exception as e:
                            output += f"错误: {str(e)}\n"
                    else:
                        output += "函数未找到\n"
                        
                elif data["type"] == "control":
                    control_type = data["control"]
                    output += f"控制语句: {control_type}\n"
                    
                self.output_text.setText(output)
                QApplication.processEvents()
                
            output += "测试序列执行完成。\n"
            self.output_text.setText(output)
            
        except Exception as e:
            output += f"执行过程中发生错误: {str(e)}\n"
            self.output_text.setText(output)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()