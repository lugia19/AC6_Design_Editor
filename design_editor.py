import zlib, struct
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QFrame, QGridLayout
from io import BytesIO

# Define the category offsets
CATEGORY_OFFSETS = {
    'weapon': 0x00000000,
    'body_part': 0x10000000,  # Head, Body, Arms, Legs
    'generator': 0x50000000,
    'booster': 0x60000000,
    'fcs': 0x70000000
}

import struct

class ChunkHeader:
    def __init__(self, signature, length, version):
        self.signature = signature
        self.length = length
        self.version = version

    def __str__(self):
        return f"{self.signature:<15} v{self.version} [{self.length:5X}h]"

    @classmethod
    def from_bytes(cls, data):
        signature = data[:0x10].rstrip(b'\x00').decode('ascii')
        length, version, unk18, unk1c = struct.unpack('<IIII', data[0x10:0x20])
        assert unk18 == 0 and unk1c == 0, "Unexpected values in chunk header"
        return cls(signature, length, version)

    def to_bytes(self):
        signature_bytes = self.signature.encode('ascii').ljust(0x10, b'\x00')
        header_bytes = struct.pack('<IIII', self.length, self.version, 0, 0)
        return signature_bytes + header_bytes

def save_id_to_equipment_id(save_id_bytes):
    """
    Convert a save ID back to its original equipment ID and category.
    :param save_id_bytes: The save ID bytes from the save file
    :return: A tuple of (equipment_id, category)
    """
    save_id = struct.unpack('<I', save_id_bytes)[0]  # Unpack as little-endian 32-bit unsigned int
    category_value = save_id & 0xF0000000
    equipment_id = save_id & 0x0FFFFFFF
    for category, offset in CATEGORY_OFFSETS.items():
        if offset == category_value:
            return equipment_id, category

    raise ValueError(f"Unknown category offset: {category_value:08X}")


def equipment_id_to_save_id(equipment_id, category):
    """
    Convert an equipment ID to its corresponding save ID.

    :param equipment_id: The original equipment ID
    :param category: The equipment category (e.g., 'main_parts', 'generators', etc.)
    :return: The save ID as a little-endian byte string
    """
    if equipment_id == -1:
        return b'\xFF\xFF\xFF\xFF'  # Return four FF bytes

    if category not in CATEGORY_OFFSETS:
        raise ValueError(f"Unknown category: {category}")

    save_id = equipment_id + CATEGORY_OFFSETS[category]

    return struct.pack('<I', save_id)  # Pack as little-endian 32-bit unsigned int



def process_assemble_bytes(assemble_bytes):
    parts = []
    weapons = []

    # Process the first 28 bytes (7 part IDs)
    for i in range(0, 28, 4):
        part_id_bytes = assemble_bytes[i:i+4]
        equipment_id, category = save_id_to_equipment_id(part_id_bytes)
        parts.append((equipment_id, category))

    # Check the separator bytes
    separator_bytes = assemble_bytes[28:32]
    if separator_bytes != b'\xFF\xFF\xFF\xFF':
        print("Invalid separator bytes.")
        return None

    # Process the remaining 32 bytes (8 weapon IDs)
    for i in range(32, 64, 4):
        if i in [48,52,56]:  # Skip weapon 5,6,7
            continue

        weapon_id_bytes = assemble_bytes[i:i+4]
        if weapon_id_bytes == b'\xFF\xFF\xFF\xFF':
            # Empty weapon slot
            weapons.append((-1, 'weapon'))
        else:
            equipment_id, category = save_id_to_equipment_id(weapon_id_bytes)
            weapons.append((equipment_id, category))

    return parts, weapons

class DesignDecompressor(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Design Decompressor')
        self.setGeometry(100, 100, 400, 400)  # Adjust the window size as needed

        layout = QVBoxLayout()

        # Design File row
        design_file_layout = QHBoxLayout()
        design_file_label = QLabel('Design File:')
        self.design_file_input = QLineEdit()
        design_file_browse_button = QPushButton('Browse')
        design_file_browse_button.clicked.connect(self.browse_design_file)
        design_file_load_button = QPushButton('Load')
        design_file_load_button.clicked.connect(self.load_design_file)
        design_file_layout.addWidget(design_file_label)
        design_file_layout.addWidget(self.design_file_input)
        design_file_layout.addWidget(design_file_browse_button)
        design_file_layout.addWidget(design_file_load_button)
        layout.addLayout(design_file_layout)

        # AC Data section
        ac_data_label = QLabel('AC Data')
        ac_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ac_data_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(ac_data_label)

        ac_data_line = QFrame()
        ac_data_line.setFrameShape(QFrame.Shape.HLine)
        ac_data_line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(ac_data_line)

        ugc_id_layout = QHBoxLayout()
        ugc_id_label = QLabel('UgcID:')
        self.ugc_id_field = QLineEdit()
        ugc_id_layout.addWidget(ugc_id_label)
        ugc_id_layout.addWidget(self.ugc_id_field)
        layout.addLayout(ugc_id_layout)

        data_name_layout = QHBoxLayout()
        data_name_label = QLabel('DataName:')
        self.data_name_field = QLineEdit()
        data_name_layout.addWidget(data_name_label)
        data_name_layout.addWidget(self.data_name_field)
        layout.addLayout(data_name_layout)

        ac_name_layout = QHBoxLayout()
        ac_name_label = QLabel('AcName:')
        self.ac_name_field = QLineEdit()
        ac_name_layout.addWidget(ac_name_label)
        ac_name_layout.addWidget(self.ac_name_field)
        layout.addLayout(ac_name_layout)

        # Parts section
        parts_label = QLabel('Parts')
        parts_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        parts_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(parts_label)

        parts_line = QFrame()
        parts_line.setFrameShape(QFrame.Shape.HLine)
        parts_line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(parts_line)

        parts_layout = QVBoxLayout()
        part_rows = [['Head', 'Body', 'Arms', 'Legs'],
                     ['Booster', 'Generator', 'FCS']]
        self.part_fields = []
        for part_row in part_rows:
            row_layout = QHBoxLayout()
            for part_name in part_row:
                part_layout = QVBoxLayout()
                part_label = QLabel(part_name)
                part_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                part_layout.addWidget(part_label)
                part_field = QLineEdit()
                part_layout.addWidget(part_field)
                row_layout.addLayout(part_layout)
                self.part_fields.append(part_field)
            row_layout.addStretch(1)  # Add stretch to make the second row fill the entire space
            parts_layout.addLayout(row_layout)
        layout.addLayout(parts_layout)

        # Weapons section
        weapons_label = QLabel('Weapons')
        weapons_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        weapons_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(weapons_label)

        weapons_line = QFrame()
        weapons_line.setFrameShape(QFrame.Shape.HLine)
        weapons_line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(weapons_line)

        weapons_layout = QHBoxLayout()
        weapon_names = ['L Hand', 'R Hand', 'L Shoulder', 'R Shoulder', 'Core Expansion']
        self.weapon_fields = []
        for weapon_name in weapon_names:
            weapon_layout = QVBoxLayout()
            weapon_label = QLabel(weapon_name)
            weapon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            weapon_layout.addWidget(weapon_label)
            weapon_field = QLineEdit()
            weapon_layout.addWidget(weapon_field)
            weapons_layout.addLayout(weapon_layout)
            self.weapon_fields.append(weapon_field)
        layout.addLayout(weapons_layout)

        # Save button
        save_button = QPushButton('Save')
        save_button.clicked.connect(self.save_file)
        layout.addWidget(save_button)

        self.setLayout(layout)
    def browse_design_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select Design File', '', 'All Files (*)')
        if file_path:
            self.design_file_input.setText(file_path)
            self.load_design_file()

    def load_design_file(self):
        file_path = self.design_file_input.text()
        if file_path:
            try:
                with open(file_path, 'rb') as file:
                    file_content = file.read()
                    if file_content.startswith(b'ASMC'):
                        decompressed_data = self.try_decompress(file_content)
                        if decompressed_data:
                            self.decompressed_data = BytesIO(decompressed_data)
                            print("Decompression successful!")
                    elif file_content.startswith(b'---- begin ----'):
                        self.decompressed_data = BytesIO(file_content)
                        print("File loaded as is.")
                    else:
                        raise ValueError("File does not start with the required bytes.")
            except FileNotFoundError as e:
                print("File not found. Please check the file path.")
                raise e
            self.read_sections()
    def try_decompress(self, data):
        try:
            # Find the position of the zlib header [0x78, 0xDA]
            start = data.find(bytes([0x78, 0xDA]))
            if start != -1:
                # Cut off the start of the file
                data = data[start:]
                decompressed_data = zlib.decompress(data)
                return decompressed_data
            else:
                print("Zlib header not found.")
                return None
        except zlib.error as e:
            print(f"Decompression failed: {e}")
            raise e

    def read_sections(self):
        self.decompressed_data.seek(0)
        data = self.decompressed_data.read()

        _, ugc_id_bytes = self.read_section_value(data, b'UgcID', b'DataName')
        _, data_name_bytes = self.read_section_value(data, b'DataName', b'AcName')
        _, ac_name_bytes = self.read_section_value(data, b'AcName', b'Assemble')

        ugc_id = self.convert_to_string(ugc_id_bytes)
        data_name = self.convert_to_string(data_name_bytes)
        ac_name = self.convert_to_string(ac_name_bytes)

        self.ugc_id_field.setText(ugc_id)
        self.data_name_field.setText(data_name)
        self.ac_name_field.setText(ac_name)

        _, assemble_bytes = self.read_section_value(data, b'Assemble', b'Coloring')
        if assemble_bytes is not None:
            parts, weapons = process_assemble_bytes(assemble_bytes)
            if parts is not None and weapons is not None:
                for i, (equipment_id, category) in enumerate(parts):
                    self.part_fields[i].setText(f"{equipment_id}")
                for i, (equipment_id, category) in enumerate(weapons):
                    if i < len(self.weapon_fields):
                        self.weapon_fields[i].setText(f"{equipment_id}")
        else:
            print("Assemble section not found.")

    def convert_to_string(self, value_bytes):
        if value_bytes is not None:
            # Strip trailing zero bytes
            while value_bytes and value_bytes[-1] == 0:
                value_bytes = value_bytes[:-1]

            value = ''.join(chr(b) for b in value_bytes[::2])
            return value
        else:
            return None

    def read_section_value(self, data, start_marker, end_marker):
        start_index = data.find(start_marker)
        if start_index == -1:
            return None

        end_index = data.find(end_marker)
        if end_index == -1:
            return None

        chunk_header_bytes = data[start_index:start_index + 0x20]
        chunk_header = ChunkHeader.from_bytes(chunk_header_bytes)
        print(chunk_header)
        value_start = start_index + 0x20
        value_bytes = data[value_start:end_index]

        # Strip trailing zero bytes
        while value_bytes and value_bytes[-1] == 0:
            value_bytes = value_bytes[:-1]

        return chunk_header, value_bytes

    def save_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save File', '', 'All Files (*)')
        if file_path:
            # Load the original file
            with open(self.design_file_input.text(), 'rb') as file:
                original_data = file.read()

            # Check if the file needs to be decompressed
            if original_data.startswith(b'ASMC'):
                original_data = self.try_decompress(original_data)
                if original_data is None:
                    raise ValueError("Decompression failed.")

            # Find the start of the "Coloring" section
            coloring_start = original_data.find(b'Coloring')
            if coloring_start == -1:
                raise ValueError("Coloring section not found in the original file.")

            # Store everything starting at the "Coloring" section
            coloring_data = original_data[coloring_start:]

            # Create a BytesIO object to store the modified data
            modified_data = BytesIO()

            # Write the "---- begin ----" header
            begin_header = ChunkHeader('---- begin ----', 0, 0)
            modified_data.write(begin_header.to_bytes())

            # Write the UgcID section
            ugc_id_bytes = self.ugc_id_field.text().encode('utf-16-le') + b"\x00\x00"
            ugc_id_header = ChunkHeader('UgcID', len(ugc_id_bytes), 0)
            modified_data.write(ugc_id_header.to_bytes())
            modified_data.write(ugc_id_bytes)

            # Write the DataName section
            data_name_bytes = self.data_name_field.text().encode('utf-16-le') + b"\x00\x00"
            data_name_header = ChunkHeader('DataName', len(data_name_bytes), 0)
            modified_data.write(data_name_header.to_bytes())
            modified_data.write(data_name_bytes)

            # Write the AcName section
            ac_name_bytes = self.ac_name_field.text().encode('utf-16-le') + b"\x00\x00"
            ac_name_header = ChunkHeader('AcName', len(ac_name_bytes), 0)
            modified_data.write(ac_name_header.to_bytes())
            modified_data.write(ac_name_bytes)

            # Write the "Assemble" section
            assemble_data = BytesIO()

            # Write the Parts
            part_fields = [
                self.part_fields[0],  # Head
                self.part_fields[1],  # Body
                self.part_fields[2],  # Arms
                self.part_fields[3],  # Legs
                self.part_fields[4],  # Booster
                self.part_fields[5],  # Generator
                self.part_fields[6]  # FCS
            ]

            part_categories = ["body_part", "body_part", "body_part", "body_part", "booster", "generator", "fcs"]
            for idx, part_field in enumerate(part_fields):
                part_id = int(part_field.text())
                assemble_data.write(equipment_id_to_save_id(part_id, part_categories[idx]))

            assemble_data.write(b'\xFF\xFF\xFF\xFF')

            # Write the Weapons
            weapon_fields = [
                self.weapon_fields[0],  # Left Hand
                self.weapon_fields[1],  # Right Hand
                self.weapon_fields[2],  # Left Shoulder
                self.weapon_fields[3],  # Right Shoulder
                299300,  # Hardcoded value
                299100,  # Hardcoded value
                -1,  # Placeholder for the four FF bytes
                self.weapon_fields[4]  # Core Expansion
            ]
            for weapon_field in weapon_fields:
                if weapon_field == -1:
                    assemble_data.write(b'\xFF\xFF\xFF\xFF')
                else:
                    if isinstance(weapon_field, int):
                        weapon_id = weapon_field
                    else:
                        weapon_id = int(weapon_field.text())
                    assemble_data.write(equipment_id_to_save_id(weapon_id, 'weapon'))

            assemble_header = ChunkHeader('Assemble', len(assemble_data.getvalue()), 3)
            modified_data.write(assemble_header.to_bytes())
            modified_data.write(assemble_data.getvalue())

            # Write the stored "Coloring" data
            modified_data.write(coloring_data)

            # Save the modified data to the selected file path
            with open(file_path, 'wb') as file:
                file.write(modified_data.getvalue())

            print(f"File saved as: {file_path}")


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
    decompressor = DesignDecompressor()
    decompressor.show()
    app.exec()