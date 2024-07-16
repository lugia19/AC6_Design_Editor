import subprocess
import sys
import os

import keyring
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QListWidget, QFileDialog, QMessageBox, QLineEdit, QLabel, QDialog)
from PyQt6.QtCore import QProcess

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        self.load_existing_paths()

    def initUI(self):
        layout = QVBoxLayout()

        # WitchyBND path
        witchy_layout = QHBoxLayout()
        witchy_layout.addWidget(QLabel("WitchyBND path:"))
        self.witchy_path = QLineEdit()
        witchy_layout.addWidget(self.witchy_path)
        witchy_browse = QPushButton("Browse")
        witchy_browse.clicked.connect(lambda: self.browse_file(self.witchy_path))
        witchy_layout.addWidget(witchy_browse)
        layout.addLayout(witchy_layout)

        # ArmoredCore bat path
        ac_layout = QHBoxLayout()
        ac_layout.addWidget(QLabel("ME2 AC6 bat path:"))
        self.ac_path = QLineEdit()
        ac_layout.addWidget(self.ac_path)
        ac_browse = QPushButton("Browse")
        ac_browse.clicked.connect(lambda: self.browse_file(self.ac_path))
        ac_layout.addWidget(ac_browse)
        layout.addLayout(ac_layout)

        # Save button
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_and_close)
        layout.addWidget(save_button)

        self.setLayout(layout)
        self.setWindowTitle('Configuration')

    def load_existing_paths(self):
        witchy_path = keyring.get_password("AC6Repack", "witchybnd_path")
        ac_path = keyring.get_password("AC6Repack", "armoredcore_bat_path")

        if witchy_path:
            self.witchy_path.setText(witchy_path)
        if ac_path:
            self.ac_path.setText(ac_path)

    def browse_file(self, line_edit):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if file_path:
            line_edit.setText(file_path)

    def save_and_close(self):
        keyring.set_password("AC6Repack", "witchybnd_path", self.witchy_path.text())
        keyring.set_password("AC6Repack", "armoredcore_bat_path", self.ac_path.text())
        self.accept()

class RepackUI(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

        # Hardcoded paths (replace with actual paths)

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput()
        stdout = bytes(data).decode("utf8")
        print(stdout, end="")

    def handle_stderr(self):
        data = self.process.readAllStandardError()
        stderr = bytes(data).decode("utf8")
        print(stderr, end="", file=sys.stderr)

    def initUI(self):
        layout = QVBoxLayout()

        # Directory list
        self.dir_list = QListWidget()
        layout.addWidget(self.dir_list)

        # Add and Remove buttons
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton('Add')
        self.remove_btn = QPushButton('Remove')
        self.add_btn.clicked.connect(self.add_directory)
        self.remove_btn.clicked.connect(self.remove_directory)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        layout.addLayout(btn_layout)

        # Kill, Repack, and Start buttons
        action_layout = QHBoxLayout()
        self.kill_btn = QPushButton('Kill')
        self.repack_btn = QPushButton('Repack')
        self.start_btn = QPushButton('Start')
        self.kill_btn.clicked.connect(self.kill_process)
        self.repack_btn.clicked.connect(self.repack)
        self.start_btn.clicked.connect(self.start)
        action_layout.addWidget(self.kill_btn)
        action_layout.addWidget(self.repack_btn)
        action_layout.addWidget(self.start_btn)
        #layout.addLayout(action_layout)

        # Restart & Repack button
        self.restart_repack_btn = QPushButton('Repack And Restart')
        self.restart_repack_btn.clicked.connect(self.restart_and_repack)
        layout.addWidget(self.restart_repack_btn)

        self.setLayout(layout)
        self.setWindowTitle('AC6 Repack Helper')
        self.show()
    def add_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if dir_path:
            self.dir_list.addItem(dir_path)

    def remove_directory(self):
        if self.dir_list.count() > 0:
            self.dir_list.takeItem(self.dir_list.count() - 1)

    def run_command(self, command_path, args=None):
        if args is None:
            args = []

        try:
            command_dir = os.path.dirname(command_path)
            command_line = f'"{command_path}" {" ".join(args)}'
            if command_dir == "":
                command_dir = None

            cmd_command = f'start /wait cmd /c "{command_line}"'

            process = subprocess.Popen(
                cmd_command,
                cwd=command_dir,
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True
            )
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd_command, output=stdout, stderr=stderr)

            print(f"{os.path.basename(command_path)} executed successfully.")
        except subprocess.CalledProcessError as error:
            print(f"Error running {os.path.basename(command_path)}: {error}")
            if error.output:
                print(f"stdout: {error.output.decode()}")
            if error.stderr:
                print(f"stderr: {error.stderr.decode()}")

    def kill_process(self):
        self.run_command("taskkill", ["/F", "/IM", "armoredcore6.exe"])

    def repack(self):
        for index in range(self.dir_list.count()):
            dir_path = self.dir_list.item(index).text()
            print(f"Repacking directory: {dir_path}")
            self.run_command(witchybnd_path, ["-p",dir_path])

    def start(self):
        self.run_command(armoredcore_bat_path)

    def restart_and_repack(self):
        self.kill_process()
        self.repack()
        self.start()


if __name__ == '__main__':
    colors_dict = {
        "primary_color": "#1A1D22",
        "secondary_color": "#282C34",
        "hover_color": "#596273",
        "text_color": "#FFFFFF",
        "toggle_color": "#4a708b",
        "green": "#3a7a3a",
        "yellow": "#faf20c",
        "red": "#7a3a3a"
    }
    stylesheet = """* {
        background-color: {primary_color};
        color: {secondary_color};
    }

    QLabel {
        color: {text_color};
    }
    QMenu {
        color: {text_color};
    }
    QLineEdit {
        background-color: {secondary_color};
        color: {text_color};
        border: 1px solid {hover_color};
    }
    QListWidget {
        color: {text_color};
    }

    QPushButton {
        background-color: {secondary_color};
        color: {text_color};
    }

    QPushButton:hover {
        background-color: {hover_color};
    }

    QCheckBox::indicator:unchecked {
        color: {hover_color};
        background-color: {secondary_color};
    }

    QCheckBox::indicator:checked {
        color: {hover_color};
        background-color: {primary_color};
    }

    QComboBox {
        background-color: {secondary_color};
        color: {text_color};
        border: 1px solid {hover_color};
    }

    QComboBox QAbstractItemView {
        background-color: {secondary_color};
        color: {text_color};
    }

    QMessageBox {
        background-color: {primary_color};
        color: {text_color};
    }

    QProgressBar {
            border: 0px solid {hover_color};
            text-align: center;
            background-color: {secondary_color};
            color: {text_color};
    }
    QProgressBar::chunk {
        background-color: {toggle_color};
    }


    QScrollBar {
        background: {primary_color};
        border: 2px {text_color};
    }
    QScrollBar::handle {
        background: {toggle_color};
    }

    QScrollBar::add-page, QScrollBar::sub-page {
        background: none;
    }

    QFrame[frameShape="4"] {
        background-color: {hover_color};
    }
        """

    for colorKey, colorValue in colors_dict.items():
        stylesheet = stylesheet.replace("{" + colorKey + "}", colorValue)

    app = QApplication([])
    app.setStyleSheet(stylesheet)

    # Show config dialog
    config_dialog = ConfigDialog()
    if config_dialog.exec():
        witchybnd_path = keyring.get_password("AC6Repack", "witchybnd_path")
        armoredcore_bat_path = keyring.get_password("AC6Repack", "armoredcore_bat_path")

        if witchybnd_path and armoredcore_bat_path:
            main_window = RepackUI()
            main_window.show()
            sys.exit(app.exec())
        else:
            QMessageBox.critical(None, "Configuration Error", "Paths not set. Please configure the paths.")
    else:
        sys.exit()
