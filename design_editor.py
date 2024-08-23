import copy
import datetime
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib, struct

import platformdirs as platformdirs
import requests
from typing import List, Union

import xmltodict
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QFrame, QGridLayout, QComboBox, QCompleter, QColorDialog, QCheckBox, \
    QStackedWidget, QSpacerItem, QSizePolicy, QMessageBox, QScrollArea, QInputDialog
from PyQt6.QtCore import Qt, QSize, QRect
from PyQt6.QtGui import QPainter, QPainterPath, QColor
from PyQt6.QtWidgets import QAbstractButton, QSizePolicy
from io import BytesIO

from customWidgets import DownloadDialog

sl2_encryption_key = bytes([0xB1, 0x56, 0x87, 0x9F, 0x13, 0x48, 0x97, 0x98, 0x70, 0x05, 0xC4, 0x87, 0x00, 0xAE, 0xF8, 0x79])

# Define the category offsets
CATEGORY_OFFSETS = {
    'weapon': 0x00000000,
    'body_part': 0x10000000,  # Head, Body, Arms, Legs
    'generator': 0x50000000,
    'booster': 0x60000000,
    'fcs': 0x70000000
}

color_section_labels = ["Head", "Core", "R arm", "L arm", "Legs", "R wep", "L wep", "R back", "L back"]
color_labels = ["Main", "Sub", "Support", "Optional", "Other", "Device"]
materials_list = []
for i in range(36):
    materials_list.append(f"{i} - Reflectiveness: {round(math.floor(i/6)*0.2, 2)} Luster: {round((i % 6) * 0.2,2)}")

device_materials_list = []
for i in range(10):
    device_materials_list.append(f"{90+i} - Brightness level {i}")

pattern_list = ["Pattern 0 (None)"]
for i in range(29):
    pattern_list.append(f"Pattern {i+1}")
pattern_size_list = ['0 - Small', '1 - Medium', '2 - Large']
weathering_list = ['Weathered 0 (None)']
for i in range(23):
    weathering_list.append(f"Weathered {i}")

TOOLS_FOLDER = platformdirs.user_data_dir(appauthor="lugia19", roaming=True, appname="ac6_tools")
VERSIONS_FILE = os.path.join(TOOLS_FOLDER, "versions.json")

witchy_dir = os.path.join(TOOLS_FOLDER, "witchybnd")
witchy_path = os.path.join(witchy_dir, "WitchyBND.exe")
texconv_path = None

def run_witchy(path:str, recursive:bool=False):
    #args = ["-p", f"\"{path}\""]
    args = [witchy_path, "-s", path]
    if recursive:
        args.insert(2, "-c")
    subprocess.run(args, check=True, capture_output=True, text=True)

def convert_to_bc7(image_path:str) -> str:
    filename = os.path.splitext(os.path.basename(image_path))[0]
    folder_path = os.path.dirname(image_path)
    subprocess.run([texconv_path, "-f", "BC7_UNORM", image_path, "-o", folder_path, "-y", "-m", "1"], check=True)
    return os.path.join(folder_path,  f"{filename}.dds")

def decrypt_file(input_file):
    with open(input_file, 'rb') as file:
        iv = file.read(16)
        ciphertext = file.read()

    cipher = AES.new(sl2_encryption_key, AES.MODE_CBC, iv)
    plaintext = cipher.decrypt(ciphertext)

    with open(input_file, 'wb') as file:
        file.write(plaintext)

def encrypt_file(input_file):
    with open(input_file, 'rb') as file:
        plaintext = file.read()

    cipher = AES.new(sl2_encryption_key, AES.MODE_CBC)
    ciphertext = cipher.encrypt(pad(plaintext, AES.block_size))

    with open(input_file, 'wb') as file:
        file.write(cipher.iv)
        file.write(ciphertext)

class CustomCheckBox(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(False)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRect(rect)

        if self.isChecked():
            painter.fillPath(path, QColor(colors_dict["secondary_color"]))  # Fill color when checked
        else:
            painter.fillPath(path, QColor(colors_dict["secondary_color"]))  # Fill color when unchecked

        painter.setPen(QColor(colors_dict["text_color"]))  # Border color
        painter.drawPath(path)

        if self.isChecked():
            check_path = QPainterPath()
            check_path.moveTo(rect.left() + 4, rect.center().y())
            check_path.lineTo(rect.center().x() - 2, rect.bottom() - 4)
            check_path.lineTo(rect.right() - 4, rect.top() + 4)
            painter.setPen(QColor(colors_dict["text_color"]))  # Check mark color
            painter.drawPath(check_path)

    def hitButton(self, pos):
        return self.contentsRect().contains(pos)

    def sizeHint(self):
        return QSize(20, 20)  # Adjust the size as needed

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


class ACThumbnail:
    width = 356
    height = 124
    unk04 = 1424

    def __init__(self):
        self.pixel_data = b''
        self.data_length = 44144
    @classmethod
    def from_image(cls, image_path):
        thumbnail = cls()

        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Copy the image to the temporary directory
            temp_image_path = os.path.join(temp_dir, os.path.basename(image_path))
            shutil.copy2(image_path, temp_image_path)

            # Resize the image
            image = QImage(temp_image_path)
            resized_image = image.scaled(thumbnail.width, thumbnail.height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            resized_image_path = os.path.join(temp_dir, "resized_image.png")
            resized_image.save(resized_image_path)

            # Convert to BC7
            bc7_image_path = convert_to_bc7(resized_image_path)

            # Load the DDS file's bytes
            with open(bc7_image_path, 'rb') as f:
                dds_data = f.read()

            header_offset = 148
            thumbnail.pixel_data = dds_data[header_offset:thumbnail.data_length]

            # Ensure the pixel data is the correct length
            if len(thumbnail.pixel_data) < thumbnail.data_length:
                thumbnail.pixel_data += b'\x00' * (thumbnail.data_length - len(thumbnail.pixel_data))
            elif len(thumbnail.pixel_data) > thumbnail.data_length:
                thumbnail.pixel_data = thumbnail.pixel_data[:thumbnail.data_length]

        return thumbnail

    def to_bytes(self):
        header = struct.pack("<IIIIII",
                             self.data_length,
                             self.unk04,
                             self.width,
                             self.height,
                             0,  # unk10
                             0)  # unk14
        return header + self.pixel_data

    @classmethod
    def empty_thumbnail(cls):
        thumbnail = cls()
        data = struct.pack("<IIIIII", thumbnail.data_length,
                           thumbnail.unk04,
                           ACThumbnail.width,
                           ACThumbnail.height,
                           0,  # unk10
                           0)  # unk14
        header = struct.unpack("<IIIIII", data[:24])
        thumbnail.data_length = header[0]
        thumbnail.unk04 = header[1]
        thumbnail.width = header[2]
        thumbnail.height = header[3]
        thumbnail.pixel_data = b'\x00' * thumbnail.data_length
        return thumbnail

    @classmethod
    def from_bytes(cls, data):
        thumbnail = cls()
        # Unpack the header
        header = struct.unpack("<IIIIII", data[:24])

        thumbnail.data_length = header[0]
        thumbnail.unk04 = header[1]
        thumbnail.width = header[2]
        thumbnail.height = header[3]
        # We don't need to store unk10 and unk14 as they should always be 0

        # Extract the pixel data
        thumbnail.pixel_data = data[24:24 + thumbnail.data_length]


        # Verify the data length
        if len(thumbnail.pixel_data) != thumbnail.data_length:
            raise ValueError("Pixel data length does not match the specified data length")

        return thumbnail

class AsmcHeader:
    def __init__(self, compressed_size, uncompressed_size):
        self.magic = b"ASMC"
        self.unk04 = 0x291222
        self.compressed_size = compressed_size
        self.uncompressed_size = uncompressed_size

    @classmethod
    def from_bytes(cls, data):
        magic, unk04, compressed_size, uncompressed_size = struct.unpack("<4sIII", data)
        assert magic == b"ASMC"
        assert unk04 == 0x291222
        return cls(compressed_size, uncompressed_size)

    def to_bytes(self):
        return struct.pack("<4sIII", self.magic, self.unk04, self.compressed_size, self.uncompressed_size)

class ASMC:
    def __init__(self, decompressed_data):
        self.header = None
        self.compressed_data = None
        if decompressed_data:
            self.compress(decompressed_data)

    @classmethod
    def from_bytes(cls, data):
        header = AsmcHeader.from_bytes(data[:16])
        compressed_data = data[16:16+header.compressed_size]
        decompressed_data = zlib.decompress(compressed_data)
        return cls(decompressed_data)

    def to_bytes(self):
        return self.header.to_bytes() + self.compressed_data

    def decompress(self) -> bytes:
        return zlib.decompress(self.compressed_data)

    def compress(self, data):
        compressed_data = zlib.compress(data, level=zlib.Z_BEST_COMPRESSION)
        self.header = AsmcHeader(len(compressed_data), len(data))
        self.compressed_data = compressed_data

class Preset:
    def __init__(self, category, date_time, design:ASMC, thumbnail):
        self.category = category
        if isinstance(date_time, datetime.datetime):
            self.date_time = self.datetime_to_bytes(date_time)
        else:
            self.date_time = date_time

        self.design = design
        self.thumbnail = thumbnail

    @staticmethod
    def datetime_to_bytes(date_time):
        file_time = Preset.datetime_to_filetime(date_time)
        system_time = Preset.datetime_to_systemtime(date_time)
        return struct.pack("<QQ", file_time, system_time)

    @staticmethod
    def datetime_to_filetime(date_time):
        # Convert datetime to Windows FILETIME
        epoch = datetime.datetime(1601, 1, 1)
        delta = date_time - epoch
        filetime = int(delta.total_seconds() * 10000000)
        return filetime

    @staticmethod
    def datetime_to_systemtime(date_time):
        # Convert datetime to PackedSystemTime
        year = date_time.year
        month = date_time.month
        day_of_week = date_time.weekday()  # 0-6, where 0 is Monday
        day = date_time.day
        hour = date_time.hour
        minute = date_time.minute
        second = date_time.second
        millisecond = date_time.microsecond // 1000

        # Pack the values according to the bit field structure
        packed = (
                (year & 0xFFF) |
                ((millisecond & 0x3FF) << 12) |
                ((month & 0xF) << 22) |
                ((day_of_week & 0x7) << 26) |
                ((day & 0x1F) << 29) |
                ((hour & 0x1F) << 34) |
                ((minute & 0x3F) << 39) |
                ((second & 0x3F) << 45)
        )

        return packed

    @classmethod
    def from_bytes(cls, data):
        # Parse the chunks
        chunks = {}
        offset = 0
        while offset < len(data):
            chunk_header = ChunkHeader.from_bytes(data[offset:offset+32])
            chunk_data = data[offset+32:offset+32+chunk_header.length]
            chunks[chunk_header.signature] = (chunk_header.version, chunk_data)
            offset += 32 + chunk_header.length
            if chunk_header.signature == "----  end  ----":
                break

        # Extract the chunk data
        category = struct.unpack("<B", chunks["Category"][1])[0]
        date_time = chunks["DateTime"][1]
        design = ASMC.from_bytes(chunks["Design"][1])
        thumbnail = ACThumbnail.from_bytes(chunks["Thumbnail"][1])

        return cls(category, date_time, design, thumbnail)

    def to_bytes(self):
        # Generate the chunk data
        category_data = struct.pack("<B", self.category)
        design_data = self.design.to_bytes()
        thumbnail_data = self.thumbnail.to_bytes()

        # Create the chunks
        chunks = [
            ("---- begin ----", b""),
            ("Category", category_data),
            ("DateTime", self.date_time),
            ("Design", design_data),
            ("Thumbnail", thumbnail_data),
            ("----  end  ----", b"")
        ]

        # Generate the preset data
        preset_data = b""
        for signature, chunk_data in chunks:
            chunk_header = ChunkHeader(signature, len(chunk_data), 0)
            preset_data += chunk_header.to_bytes() + chunk_data

        return preset_data

class UserDesignData:
    def __init__(self, unk0c, unk04, unk08, presets):
        self.unk0c = unk0c
        self.unk04 = unk04
        self.unk08 = unk08
        self.presets = presets

    @classmethod
    def from_bytes(cls, data):
        # Extract the inner size from the header
        inner_size = struct.unpack("<I", data[:4])[0]

        # Extract the hash from the end of the inner content
        stored_hash = data[4+inner_size - 16:inner_size+4]

        # Extract the main content (excluding size field and hash)
        content = data[4:inner_size - 16+4]

        # Parse the header
        header = content[:16]
        unk04, unk08, unk0c, preset_count = struct.unpack("<IIII", header)

        # Parse presets
        presets = []
        offset = 16
        for _ in range(preset_count):
            preset_data = content[offset:]
            preset = Preset.from_bytes(preset_data)
            presets.append(preset)
            offset += len(preset.to_bytes())

        instance = cls(unk0c, unk04, unk08, presets)
        return instance

    def to_bytes(self):
        inner_size = 4194320

        # Calculate the inner content
        header = struct.pack("<IIII", 0, 0, len(self.presets), len(self.presets))
        preset_data = b"".join(preset.to_bytes() for preset in self.presets)

        # Pad the preset_data with zeros to reach the fixed size
        padding_length = inner_size - len(header) - len(preset_data) - 16  # 16 is for MD5 hash
        if padding_length < 0:
            raise ValueError("Preset data exceeds the fixed inner size")

        padded_preset_data = preset_data + b'\x00' * padding_length

        inner_content = header + padded_preset_data

        # Calculate MD5 hash
        md5_hash = hashlib.md5(inner_content).digest()

        # Create the full content with size, inner content, and hash
        full_content = struct.pack("<I", inner_size) + inner_content + md5_hash

        # Calculate padding
        padding_size = (16 - (len(full_content) % 16)) % 16
        full_content += b'\x0C' * padding_size

        return full_content

    def add_preset(self, preset):
        self.presets.append(preset)

    def remove_preset(self, index):
        if 0 <= index < len(self.presets):
            del self.presets[index]

class ColorRowData:
    def __init__(self, color_name, color=None, material=None, pattern=False):
        self.color_name = color_name
        self.color = color or QColor(255, 255, 255)  # Default to white if no color is provided
        self.material = material
        self.pattern = pattern

class ColoringSectionData:
    def __init__(self, name):
        self.name = name
        self.color_rows = []
        self.pattern_number = None
        self.pattern_size = None
        self.pattern_colors = []
        self.weathering = None

    def to_bytes(self):
        data = bytearray()
        data.extend(b'\xff\x00\x00\x00')  # unk00
        data.extend(struct.pack('<h', int(self.weathering.split(" ")[1]) or 0))  # weathering
        data.extend(b'\x00\x00')  # unk06

        for color_row in self.color_rows:
            color = color_row.color
            data.extend(struct.pack('<BBBB', color.red(), color.green(), color.blue(), color.alpha()))

        for color_row in self.color_rows:
            material = color_row.material
            material_index = 0  # Default to 0 if material is not found
            if material:
                material_index = int(material.split(' - ')[0])  # Extract the material index from the string
            data.extend(struct.pack('<h', material_index))

        data.extend(struct.pack('<B', int(self.pattern_number.split(" ")[1]) or 0))  # patternDesign
        data.extend(struct.pack('<B', int(self.pattern_size.split(" - ")[0]) or 0))  # patternSize
        data.extend(b'\x00\x00')  # unk2e

        for color in self.pattern_colors:
            data.extend(struct.pack('<BBBB', color.red(), color.green(), color.blue(), color.alpha()))

        # Calculate unk40 based on the pattern checkbox states
        unk40 = 0b00111111  # Default value with all bits set to 1
        for i, color_row in enumerate(reversed(self.color_rows[:5])):
            if color_row.pattern:
                unk40 &= ~(1 << (i + 2))  # Set the corresponding bit to 0 if pattern is enabled

        data.extend(struct.pack('<H', unk40))  # unk40
        data.extend(b'\x00\x00')  # unk42

        return bytes(data)

    @classmethod
    def from_bytes(cls, name, data):
        coloring_section = cls(name)

        # Skip unk00
        weathering = struct.unpack('<h', data[4:6])[0]
        coloring_section.weathering = weathering

        # Skip unk06

        for i in range(6):
            start = 8 + i * 4
            end = start + 4
            rgba = struct.unpack('<BBBB', data[start:end])
            color = QColor(*rgba)
            coloring_section.color_rows.append(ColorRowData(color_labels[i], color=color))

        for i in range(6):
            start = 32 + i * 2
            end = start + 2
            material_index = struct.unpack('<h', data[start:end])[0]
            material = f"{material_index}"  # Placeholder material string
            coloring_section.color_rows[i].material = material

        coloring_section.pattern_number = data[44]
        coloring_section.pattern_size = data[45]

        # Skip unk2e

        for i in range(4):
            start = 48 + i * 4
            end = start + 4
            rgba = struct.unpack('<BBBB', data[start:end])
            color = QColor(*rgba)
            coloring_section.pattern_colors.append(color)
        if len(data) < 66:
            data += b"\x00\x00"
        unk40 = struct.unpack('<H', data[64:66])[0]
        for i, color_row in enumerate(reversed(coloring_section.color_rows[:5])):
            color_row.pattern = not bool(unk40 & (1 << (i + 2)))

        # Skip unk42

        return coloring_section


class ColorRow(QWidget):
    def __init__(self, color_label, parent=None):
        super().__init__(parent)
        self.color_name = color_label
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(self.color_name)
        layout.addWidget(self.label)

        self.color_picker = QPushButton()
        self.color_picker.setStyleSheet(f'background-color: gray;')
        self.color_picker.clicked.connect(self.open_color_picker)
        layout.addWidget(self.color_picker)

        self.material_dropdown = QComboBox()
        self.material_dropdown.addItems(materials_list)
        layout.addWidget(self.material_dropdown)

        checkbox_container = QHBoxLayout()
        self.pattern_checkbox = CustomCheckBox()
        checkbox_container.addWidget(self.pattern_checkbox)
        self.pattern_checkbox_padder = QLabel("")
        checkbox_container.addWidget(self.pattern_checkbox_padder)
        #checkbox_container.addStretch(1)
        layout.addLayout(checkbox_container)
        self.row_layout = layout
        self.setLayout(layout)

    def open_color_picker(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.color_picker.setStyleSheet(f'background-color: {color.name()};')

    def set_row_type(self, row_type):
        if row_type == "full":
            self.material_dropdown.setVisible(True)
            self.pattern_checkbox.setVisible(True)
            self.pattern_checkbox_padder.setVisible(True)
        elif row_type == "device":
            self.material_dropdown.clear()
            self.material_dropdown.addItems(device_materials_list)
            self.pattern_checkbox.setVisible(False)
            self.pattern_checkbox_padder.setVisible(False)
        elif row_type == "colors-only":
            self.material_dropdown.setVisible(False)
            self.pattern_checkbox.setVisible(False)
            self.pattern_checkbox_padder.setVisible(False)

    def import_settings(self, settings):
        self.color_picker.setStyleSheet(f'background-color: {settings.color.name()};')
        if settings.material:
            if settings.material.isnumeric():
                index = self.material_dropdown.findText(f"{settings.material} - ", flags=Qt.MatchFlag.MatchContains)
            else:
                index = self.material_dropdown.findText(settings.material, flags=Qt.MatchFlag.MatchContains)
            if index >= 0:
                self.material_dropdown.setCurrentIndex(index)
        self.pattern_checkbox.setChecked(settings.pattern)

    def export_settings(self):
        return ColorRowData(
            self.label.text(),
            QColor(self.color_picker.palette().button().color()),
            self.material_dropdown.currentText(),
            self.pattern_checkbox.isChecked()
        )

class ColoringSection(QWidget):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Add a label with the section name
        self.name_label = QLabel(self.name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("font-weight: bold;")
        new_font = self.name_label.font()
        new_font.setPointSize(12)
        self.name_label.setFont(new_font)
        layout.addWidget(self.name_label)

        coloring_line = QFrame()
        coloring_line.setFrameShape(QFrame.Shape.HLine)
        coloring_line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(coloring_line)

        coloring_layout = QVBoxLayout()

        # Column labels
        labels_layout = QHBoxLayout()
        labels_layout.addWidget(QLabel('Color name'))
        labels_layout.addWidget(QLabel('Color picker'))
        labels_layout.addWidget(QLabel('Material'))
        labels_layout.addWidget(QLabel('Print Pattern'))
        coloring_layout.addLayout(labels_layout)

        self.color_rows = []

        # Six rows of color pickers
        for i, color_label in enumerate(color_labels):
            color_row = ColorRow(color_label)
            if i == len(color_labels) - 1:  # Last row
                color_row.set_row_type("device")
                color_row.row_layout.addWidget(QLabel(""))
            else:
                color_row.set_row_type("full")
            coloring_layout.addWidget(color_row)
            self.color_rows.append(color_row)

        # Pattern and Pattern Size dropdowns
        hbox_wrap = QHBoxLayout()
        pattern_label = QLabel("Pattern")
        pattern_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        hbox_wrap.addStretch()
        hbox_wrap.addWidget(pattern_label)
        hbox_wrap.addStretch()
        coloring_layout.addLayout(hbox_wrap)


        pattern_layout = QHBoxLayout()
        pattern_layout.addWidget(QLabel('Pattern number'))
        self.pattern_dropdown = QComboBox()
        self.pattern_dropdown.addItems(pattern_list)  # Dummy options
        pattern_layout.addWidget(self.pattern_dropdown)
        pattern_layout.addWidget(QLabel('Pattern Size'))
        self.pattern_size_dropdown = QComboBox()
        self.pattern_size_dropdown.addItems(pattern_size_list)  # Dummy options
        pattern_layout.addWidget(self.pattern_size_dropdown)
        coloring_layout.addLayout(pattern_layout)

        # Two rows with two color pickers each
        self.pattern_color_rows = []
        for i in range(2):
            color_pickers_layout = QHBoxLayout()
            for j in range(2):
                color_row = ColorRow(f"Color {(i + 1) + (j + 1)}")
                color_row.set_row_type("colors-only")
                color_pickers_layout.addWidget(color_row)
                self.pattern_color_rows.append(color_row)
            coloring_layout.addLayout(color_pickers_layout)

        # Weathering dropdown
        weathering_layout = QHBoxLayout()
        weathering_layout.addWidget(QLabel('Weathering:'))
        self.weathering_dropdown = QComboBox()
        self.weathering_dropdown.addItems(weathering_list)  # Dummy options
        weathering_layout.addWidget(self.weathering_dropdown)
        weathering_layout.addWidget(QLabel(""))
        weathering_layout.addWidget(QLabel(""))
        coloring_layout.addLayout(weathering_layout)

        layout.addLayout(coloring_layout)

        self.setLayout(layout)

    def open_color_picker(self, button):
        color = QColorDialog.getColor()
        if color.isValid():
            button.setStyleSheet(f'background-color: {color.name()};')

    def import_settings(self, settings):
        for i, color_row_settings in enumerate(settings.color_rows):
            if i < len(self.color_rows):
                self.color_rows[i].import_settings(color_row_settings)

        index = self.pattern_dropdown.findText(str(settings.pattern_number), flags=Qt.MatchFlag.MatchContains)
        if index >= 0:
            self.pattern_dropdown.setCurrentIndex(index)

        index = self.pattern_size_dropdown.findText(str(settings.pattern_size), flags=Qt.MatchFlag.MatchContains)
        if index >= 0:
            self.pattern_size_dropdown.setCurrentIndex(index)

        for i, color in enumerate(settings.pattern_colors):
            if i < len(self.pattern_color_rows):
                self.pattern_color_rows[i].import_settings(ColorRowData(f"Pattern Color {i+1}", color))

        index = self.weathering_dropdown.findText(str(settings.weathering), flags=Qt.MatchFlag.MatchContains)
        if index >= 0:
            self.weathering_dropdown.setCurrentIndex(index)

    def export_settings(self):
        settings = ColoringSectionData(self.name_label.text())
        for color_row in self.color_rows:
            settings.color_rows.append(color_row.export_settings())

        settings.pattern_size = self.pattern_size_dropdown.currentText()
        settings.pattern_number = self.pattern_dropdown.currentText()

        for pattern_color_row in self.pattern_color_rows:
            settings.pattern_colors.append(QColor(pattern_color_row.color_picker.palette().button().color()))

        settings.weathering = self.weathering_dropdown.currentText()

        return settings

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

def process_coloring_bytes(coloring_bytes):
    coloring_sections = []
    section_index = 0

    # Process the color sets
    for i in range(14):
        start = i * 68
        end = start + 68
        color_set_bytes = coloring_bytes[start:end]

        if i in [6, 7, 9, 10, 11]:
            continue  # Skip the unknown sections
        coloring_section = ColoringSectionData.from_bytes(color_section_labels[section_index], color_set_bytes)
        coloring_sections.append(coloring_section)
        section_index += 1

    return coloring_sections


def read_section_value(data, start_marker, instance=0):
    start_index = -1
    instance_count = 0
    search_start = 0

    while instance_count <= instance:
        start_index = data.find(start_marker, search_start)
        if start_index == -1:
            return None
        instance_count += 1
        search_start = start_index + len(start_marker)

    chunk_header_bytes = data[start_index:start_index + 0x20]
    chunk_header = ChunkHeader.from_bytes(chunk_header_bytes)
    value_start = start_index + 0x20
    value_bytes = data[value_start:value_start + chunk_header.length]

    # Strip trailing zero bytes
    while value_bytes and value_bytes[-1] == 0:
        value_bytes = value_bytes[:-1]

    return chunk_header, value_bytes


def convert_to_string(value_bytes):
    if value_bytes is not None:
        # Strip trailing zero bytes
        while value_bytes and value_bytes[-1] == 0:
            value_bytes = value_bytes[:-1]

        value = ''.join(chr(b) for b in value_bytes[::2])
        return value
    else:
        return None


class DesignDecompressor(QWidget):
    def __init__(self):
        super().__init__()
        self.current_section = 0
        self.coloring_sections:List[ColoringSection] = []
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Design Editor')
        self.setGeometry(100, 100, 400, 400)  # Adjust the window size as needed

        layout = QVBoxLayout()

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

        if not os.path.exists("parts.json"):
            parts_base = {
                "Protectors": {
                    "Head": [],
                    "Core": [],
                    "Arms": [],
                    "Legs": []
                },
                "Internals": {
                    "Booster": [],
                    "Generator": [],
                    "FCS": []
                },
                "Weapons": {
                    "LHand": [],
                    "RHand": [],
                    "LBack": [],
                    "RBack": [],
                    "CExpansion": []
                }
            }
            with open("parts.json", "w") as file:
                json.dump(parts_base, file)


        parts_layout = QVBoxLayout()
        part_rows = [['Head', 'Core'],
                     ['Arms', 'Legs'],
                     ['Booster', 'Generator', 'FCS']]
        self.part_fields = []
        for part_row in part_rows:
            row_layout = QHBoxLayout()
            for idx, part_name in enumerate(part_row):
                part_layout = QVBoxLayout()
                part_label = QLabel(part_name)
                part_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                part_layout.addWidget(part_label)
                part_field = QComboBox()
                part_field.setEditable(True)
                part_field.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
                completer = part_field.completer()
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

                part_field.setMaximumWidth(400)  # Set a maximum width for the part comboboxes
                part_layout.addWidget(part_field)
                row_layout.addLayout(part_layout)
                #if len(part_row) < 3 and idx == 0:
                #    row_layout.addStretch(1)
                self.part_fields.append(part_field)
            #row_layout.addStretch(1)
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

        weapons_layout = QVBoxLayout()
        weapon_rows = [
            ['Left Hand', 'Right Hand'],
            ['Left Shoulder', 'Right Shoulder'],
            ['Core Expansion']
        ]
        self.weapon_fields = []
        for weapon_row in weapon_rows:
            row_layout = QHBoxLayout()
            for weapon_name in weapon_row:
                if len(weapon_row) == 1:
                    row_layout.addStretch(1)
                weapon_layout = QVBoxLayout()
                weapon_label = QLabel(weapon_name)
                weapon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                weapon_layout.addWidget(weapon_label)
                weapon_field = QComboBox()
                weapon_field.setMaximumWidth(400)  # Set a maximum width for the part comboboxes
                weapon_field.setEditable(True)
                weapon_field.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

                completer = weapon_field.completer()
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

                weapon_layout.addWidget(weapon_field)
                row_layout.addLayout(weapon_layout)
                if len(weapon_row) == 1:
                    row_layout.addStretch(1)
                self.weapon_fields.append(weapon_field)
            #row_layout.addStretch(1)
            weapons_layout.addLayout(row_layout)
        layout.addLayout(weapons_layout)

        self.import_regbin("resources/regulation.bin")

        # Navigation row
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton('←')
        self.prev_button.clicked.connect(self.prev_section)
        self.prev_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['primary_color']}")
        self.next_button = QPushButton('→')
        self.next_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['toggle_color']}")

        self.next_button.clicked.connect(self.next_section)

        coloring_label = QLabel('Colors')
        coloring_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        coloring_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(coloring_label)
        nav_layout.addWidget(self.next_button)
        layout.addLayout(nav_layout)

        copy_all_layout = QHBoxLayout()
        copy_all_layout.addWidget(QLabel(""))
        self.copy_to_all_button = QPushButton('Copy to All')
        self.copy_to_all_button.clicked.connect(self.copy_to_all_sections)
        copy_all_layout.addWidget(self.copy_to_all_button)
        copy_all_layout.addWidget(QLabel(""))
        layout.addLayout(copy_all_layout)
        # Create coloring sections
        self.coloring_stack = QStackedWidget()
        for name in color_section_labels:
            section = ColoringSection(name)
            self.coloring_sections.append(section)
            self.coloring_stack.addWidget(section)
        layout.addWidget(self.coloring_stack)


        # UserImage & Decals section
        userimage_label = QLabel('UserImage & Decals')
        userimage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        userimage_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(userimage_label)

        userimage_line = QFrame()
        userimage_line.setFrameShape(QFrame.Shape.HLine)
        userimage_line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(userimage_line)

        userimage_layout = QHBoxLayout()
        userimage_layout.addWidget(QLabel("Design file for UserImage & Decals:"))
        self.userimage_textbox = QLineEdit()
        userimage_layout.addWidget(self.userimage_textbox)

        browse_button = QPushButton('Browse')
        browse_button.clicked.connect(self.browse_userimage_file)
        userimage_layout.addWidget(browse_button)

        erase_button = QPushButton('Erase')
        erase_button.clicked.connect(self.erase_userimage_file)
        userimage_layout.addWidget(erase_button)

        layout.addLayout(userimage_layout)


        self.editor_widget = QWidget()
        self.editor_widget.setLayout(layout)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)  # Make the scroll area resizable
        self.scroll_area.setWidget(self.editor_widget)
        self.root_layout = QVBoxLayout()
        self.root_layout.addWidget(self.scroll_area)

        # Bottom row
        bottom_row_layout = QHBoxLayout()
        load_from_file_button = QPushButton('Load from .design')
        load_from_file_button.clicked.connect(self.browse_design_file)
        load_from_save_button = QPushButton('Load from .sl2')
        load_from_save_button.clicked.connect(self.load_from_save)
        import_regbin_button = QPushButton('Import mod parts')
        import_regbin_button.clicked.connect(self.import_regbin)

        bottom_row_layout.addWidget(load_from_file_button)
        bottom_row_layout.addWidget(load_from_save_button)

        bottom_row_layout.addWidget(QLabel(""))
        bottom_row_layout.addWidget(QLabel(""))
        bottom_row_layout.addWidget(import_regbin_button)
        bottom_row_layout.addWidget(QLabel(""))
        bottom_row_layout.addWidget(QLabel(""))

        save_design_button = QPushButton('Save .design')
        save_design_button.clicked.connect(self.save_design_file)
        save_to_sl2_button = QPushButton('Save to .sl2')
        save_to_sl2_button.clicked.connect(self.save_to_sl2)
        bottom_row_layout.addWidget(save_to_sl2_button)
        bottom_row_layout.addWidget(save_design_button)
        self.root_layout.addLayout(bottom_row_layout)

        self.stored_original_design = None

        self.setLayout(self.root_layout)
        self.fix_size()

    def browse_userimage_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select Design File', '', 'All Files (*)')
        if file_path:
            self.userimage_textbox.setText(file_path)
            self.stored_original_design = None

    def erase_userimage_file(self):
        self.userimage_textbox.clear()

    def fix_size(self):
        # Get screen size
        screen = QtWidgets.QApplication.primaryScreen()
        self.adjustSize()

        if not hasattr(self, "editor_widget"):
            return  # Whoops, too early.

        # Now get the sizeHint of the settings_widget and compare it with the screen size

        recommended_size = self.editor_widget.sizeHint()
        screen_size = screen.availableGeometry()
        screen_size = QtCore.QSize(int(screen_size.width() * 8 / 10), int(screen_size.height() * 8 / 10))

        # Calculate the size to set (accounting for the scroll bars)
        size_to_set = QtCore.QSize(
            min(recommended_size.width() + self.scroll_area.verticalScrollBar().width() * 3, screen_size.width()),
            min(recommended_size.height() + self.scroll_area.horizontalScrollBar().height(), screen_size.height())
        )

        # Set the size of the dialog
        self.resize(size_to_set)

    def prev_section(self):
        if self.current_section > 0:
            self.current_section -= 1
            self.update_section()

    def next_section(self):
        if self.current_section < 8:
            self.current_section += 1
            self.update_section()

    def update_section(self):
        self.coloring_stack.setCurrentIndex(self.current_section)
        if self.current_section > 0:
            self.prev_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['toggle_color']}")
        else:
            self.prev_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['primary_color']}")

        if self.current_section < len(color_section_labels) - 1:
            self.next_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['toggle_color']}")
        else:
            self.next_button.setStyleSheet(f"font-weight: bold; background-color: {colors_dict['primary_color']}")
        self.prev_button.setEnabled(self.current_section > 0)
        self.next_button.setEnabled(self.current_section < len(color_section_labels) - 1)

    def copy_to_all_sections(self):
        current_section = self.coloring_sections[self.current_section]
        settings = current_section.export_settings()

        for i, section in enumerate(self.coloring_sections):
            if i != self.current_section:
                # Create a new settings object with the target section's name
                new_settings = ColoringSectionData(section.name)
                # Copy all other settings from the current section
                new_settings.color_rows = settings.color_rows
                new_settings.pattern_number = settings.pattern_number
                new_settings.pattern_size = settings.pattern_size
                new_settings.pattern_colors = settings.pattern_colors
                new_settings.weathering = settings.weathering

                section.import_settings(new_settings)

        QMessageBox.information(self, "Copy Complete", "Settings copied to all sections.")

    def load_parts(self):
        protector_types = ["Head", "Core", "Arms", "Legs"]
        inner_types = ["Booster", "Generator", "FCS"]

        with open("parts.json", 'r') as file:
            data = json.load(file)
            protectors = data["Protectors"]
            internals = data["Internals"]
            for i, part_field in enumerate(self.part_fields):
                part_field.clear()
                if i < 4:  # Head, Core, Arms, Legs
                    part_type = protector_types[i]
                    filtered_parts = [f"{part['ID']} {part['Name']}" for part in protectors[part_type]]
                else:  # Booster, Generator, FCS
                    part_type = inner_types[i-4]
                    filtered_parts = [f"{part['ID']} {part['Name']}" for part in internals[part_type]]
                part_field.addItems(filtered_parts)

    def load_weapons(self):
        cwd = os.getcwd()
        slots = ["LHand", "RHand", "LBack", "RBack", "CExpansion"]
        with open("parts.json", 'r') as file:
            data = json.load(file)
            weapons = data["Weapons"]
            for i, weapon_field in enumerate(self.weapon_fields):
                weapon_field.clear()
                weapon_type = slots[i]
                filtered_weapons = [f"{weapon['ID']} {weapon['Name']}" for weapon in weapons[weapon_type]]
                weapon_field.addItem("-1 Empty")
                weapon_field.addItems(filtered_weapons)

    def import_regbin(self, file_override=None):
        if file_override:
            file_path = file_override
            #Don't bother re-parsing it if it's the same...
            hash_path = os.path.join(os.path.dirname(file_path), "regbin_hash.txt")
            with open(file_path, "rb") as regbin:
                new_hash = hashlib.sha1(regbin.read()).hexdigest().strip()
            if os.path.exists(hash_path):
                old_hash = open(hash_path, "r").read().strip()
                if new_hash == old_hash:
                    self.load_parts()
                    self.load_weapons()
                    return
                else:
                    open(hash_path, "w").write(new_hash)
            else:
                open(hash_path, "w").write(new_hash)
        else:
            file_path, _ = QFileDialog.getOpenFileName(self, 'Select regulation.bin', '', 'regulation.bin (regulation.bin)')
        if file_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                with open("parts.json", 'r') as file:
                    parts_data = json.load(file)
                # Copy the regulation.bin file to the temporary directory
                shutil.copy(file_path, os.path.join(temp_dir, 'regulation.bin'))

                # Unpack regulation.bin
                run_witchy(os.path.join(temp_dir, 'regulation.bin'), False)

                # List of .param files to process
                param_files = [
                    'EquipParamProtector.param',
                    'EquipParamWeapon.param',
                    'EquipParamFcs.param',
                    'EquipParamGenerator.param',
                    'EquipParamBooster.param'
                ]

                for param_file in param_files:
                    param_path = os.path.join(temp_dir, 'regulation-bin', param_file)
                    xml_path = f'{param_path}.xml'

                    # Unpack the .param file
                    run_witchy(param_path, False)

                    # Open and process the generated XML file
                    with open(xml_path, 'r') as xml_file:
                        xml_content = xml_file.read()
                        xml_data = xmltodict.parse(xml_content)
                        rows = xml_data['param']['rows']['row']
                        if param_file == "EquipParamProtector.param":
                            for row in rows:
                                part_id = row['@id']
                                part_name = row.get('@paramdexName', '')

                                part_types = []
                                if row.get('@headEquip') == '1':
                                    part_types.append('Head')
                                if row.get('@bodyEquip') == '1':
                                    part_types.append('Core')
                                if row.get('@armEquip') == '1':
                                    part_types.append('Arms')
                                if row.get('@legEquip') == '1':
                                    part_types.append('Legs')

                                # Check if the part already exists in parts_data
                                existing_part = None
                                for category in parts_data['Protectors'].values():
                                    for part in category:
                                        if part['ID'] == part_id:
                                            existing_part = part
                                            break
                                    if existing_part:
                                        break

                                if existing_part:
                                    # Update the part name
                                    existing_part['Name'] = part_name
                                    # Remove the part from categories where it shouldn't be
                                    for category, parts in parts_data['Protectors'].items():
                                        if category not in part_types and existing_part in parts:
                                            parts.remove(existing_part)
                                else:
                                    # Add the part to the appropriate categories
                                    for part_type in part_types:
                                        parts_data['Protectors'][part_type].append({'ID': part_id, 'Name': part_name})

                        elif param_file == "EquipParamWeapon.param":
                            for row in rows:
                                part_id = row['@id']
                                part_name = row.get('@paramdexName', '')

                                part_types = []
                                if row.get('@equipFrontRightSlot') == '1':
                                    part_types.append('RHand')
                                if row.get('@equipFrontLeftSlot') == '1':
                                    part_types.append('LHand')
                                if row.get('@equipBackRightSlot') == '1':
                                    part_types.append('RBack')
                                if row.get('@equipBackLeftSlot') == '1':
                                    part_types.append('LBack')

                                # Check if the part already exists in parts_data
                                existing_part = None
                                for category in parts_data['Weapons'].values():
                                    for part in category:
                                        if part['ID'] == part_id:
                                            existing_part = part
                                            break
                                    if existing_part:
                                        break

                                if existing_part:
                                    # Update the part name
                                    existing_part['Name'] = part_name
                                    # Remove the part from categories where it shouldn't be
                                    for category, parts in parts_data['Weapons'].items():
                                        if category not in part_types and existing_part in parts:
                                            parts.remove(existing_part)
                                else:
                                    # Add the part to the appropriate categories
                                    for part_type in part_types:
                                        parts_data['Weapons'][part_type].append({'ID': part_id, 'Name': part_name})

                        elif param_file in ["EquipParamFcs.param", "EquipParamGenerator.param", "EquipParamBooster.param"]:
                            category = param_file.replace("EquipParam", "").replace(".param", "")
                            if category.upper() == "FCS": category = category.upper()
                            for row in rows:
                                part_id = row['@id']
                                part_name = row.get('@paramdexName', '')

                                # Check if the part already exists in parts_data
                                existing_part = None
                                for part in parts_data['Internals'][category]:
                                    if part['ID'] == part_id:
                                        existing_part = part
                                        break

                                if existing_part:
                                    # Update the part name
                                    existing_part['Name'] = part_name
                                else:
                                    # Add the part to the appropriate category
                                    parts_data['Internals'][category].append({'ID': part_id, 'Name': part_name})

                # Check if msg/engus/item.msgbnd.dcx exists
                msg_folder_path = os.path.join(os.path.dirname(file_path), 'msg')
                if os.path.exists(msg_folder_path):
                    shutil.copytree(msg_folder_path, os.path.join(temp_dir, 'msg'))

                msg_file_path = os.path.join(temp_dir, 'msg', 'engus', 'item.msgbnd.dcx')
                if os.path.exists(msg_file_path):
                    # Unpack item.msgbnd.dcx
                    run_witchy(msg_file_path, True)

                    # Dictionary to map fmg.xml files to their corresponding categories
                    fmg_category_map = {
                        'FCS名.fmg.xml': 'FCS',
                        'ジェネレーター名.fmg.xml': 'Generator',
                        'ブースター名.fmg.xml': 'Booster',
                        '武器名.fmg.xml': 'Weapons',
                        '防具名.fmg.xml': 'Protectors'
                    }

                    # Process each fmg.xml file
                    def update_part_name(part, texts):
                        if not part['Name']:
                            for text in texts:
                                if text['@id'] == part['ID']:
                                    part['Name'] = text['#text']
                                    break

                    for fmg_file, category in fmg_category_map.items():
                        fmg_path = os.path.join(os.path.dirname(msg_file_path), 'item-msgbnd-dcx', fmg_file)
                        if os.path.exists(fmg_path):
                            with open(fmg_path, 'r', encoding='utf-8') as fmg_file:
                                fmg_content = fmg_file.read()
                                fmg_data = xmltodict.parse(fmg_content)
                                texts = fmg_data['fmg']["entries"]['text']

                                if category == 'Weapons' or category == "Protectors":
                                    for item_category in parts_data[category].values():
                                        for part in item_category:
                                            update_part_name(part, texts)
                                else:
                                    for part in parts_data['Internals'][category]:
                                        update_part_name(part, texts)

                with open("parts.json", 'w') as file:
                    json.dump(parts_data, file, indent=4)

                # Cleanup will be handled automatically by tempfile
                self.load_parts()
                self.load_weapons()

    def browse_design_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select Design File', '', 'All Files (*)')
        if file_path:
            self.load_design_file(file_path)

    def load_design_file(self, file_path):
        if file_path:
            try:
                with open(file_path, 'rb') as file:
                    file_content = file.read()
                    if file_content.startswith(b'ASMC'):
                        decompressed_data = self.try_decompress(file_content)
                        if decompressed_data:
                            print("Decompression successful!")
                    elif file_content.startswith(b'---- begin ----'):
                        decompressed_data = file_content
                        print("File loaded as is.")
                    else:
                        raise ValueError("File does not start with the required bytes.")
            except FileNotFoundError as e:
                print("File not found. Please check the file path.")
                raise e
            self.read_sections(decompressed_data)
            self.stored_original_design = None
            self.userimage_textbox.setText(file_path)

    def load_from_save(self):
        appdata_path = os.path.expandvars("%AppData%")
        default_dir = os.path.join(appdata_path, "ArmoredCore6")
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select Save File', default_dir, 'Save Files (*.sl2)')
        if file_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Copy the selected .sl2 file to the temporary directory
                temp_sl2_path = os.path.join(temp_dir, os.path.basename(file_path))
                shutil.copy(file_path, temp_sl2_path)

                # Unpack the .sl2 file using run_witchy
                run_witchy(temp_sl2_path, True)

                # Find the unpacked folder
                unpacked_folder = f"{os.path.splitext(os.path.basename(file_path))[0]}-sl2"
                unpacked_path = os.path.join(temp_dir, unpacked_folder)

                all_presets:List[Preset] = []
                for current_data in range(2, 7):  # USER_DATA002 to USER_DATA006
                    data_path = os.path.join(unpacked_path, f"USER_DATA0{str(current_data).zfill(2)}")
                    if os.path.exists(data_path):
                        decrypt_file(data_path)
                        with open(data_path, "rb") as file:
                            data = file.read()
                            user_data = UserDesignData.from_bytes(data)
                            all_presets.extend(user_data.presets)  # Assuming presets are stored in a 'presets' attribute
                all_designs = [x.design.decompress() for x in all_presets]

                design_labels = []
                for design in all_designs:
                    _, data_name_bytes = read_section_value(design, b'DataName')
                    _, ac_name_bytes = read_section_value(design, b'AcName')

                    data_name = convert_to_string(data_name_bytes)
                    ac_name = convert_to_string(ac_name_bytes)
                    design_labels.append(f"{ac_name} // {data_name}")



                # Show a dialog with a dropdown listing the design labels
                design_label, ok = QInputDialog.getItem(self, "Select Design", "Choose a design:", design_labels, 0, False)
                if ok and design_label:
                    design_index = design_labels.index(design_label)
                    chosen_design = all_designs[design_index]
                    self.read_sections(chosen_design)
                    self.userimage_textbox.setText("Loaded from .sl2")
                    self.stored_original_design = chosen_design

    def try_decompress(self, data):
        try:
            # Find the position of the zlib header [0x78, 0xDA]
            start = data.find(bytes([0x78, 0xDA]))
            if start != -1:
                # Cut off the extra header
                data = data[start:]
                try:
                    decompressed_data = zlib.decompress(data)
                except zlib.error as e:
                    #Flip the last 4 bytes and try again.
                    flipped_data = data[:-4] + data[-4:][::-1]
                    try:
                        decompressed_data = zlib.decompress(flipped_data)
                    except zlib.error as ex:
                        #Okay, fuck it, we're just going to ignore the checksum.
                        raw_data = data[2:-4]
                        decompressor = zlib.decompressobj(wbits=-zlib.MAX_WBITS)
                        decompressed_data = decompressor.decompress(raw_data)
                        remaining_data = decompressor.unused_data
                        if remaining_data:
                            print("Warning: Decompression completed with remaining data.")
                            print("Remaining data:", remaining_data)


                return decompressed_data
            else:
                print("Zlib header not found.")
                return None
        except zlib.error as e:
            print(f"Decompression failed: {e}")
            raise e

    def read_sections(self, decompressed_bytes):
        _, ugc_id_bytes = read_section_value(decompressed_bytes, b'UgcID')
        _, data_name_bytes = read_section_value(decompressed_bytes, b'DataName')
        _, ac_name_bytes = read_section_value(decompressed_bytes, b'AcName')

        ugc_id = convert_to_string(ugc_id_bytes)
        data_name = convert_to_string(data_name_bytes)
        ac_name = convert_to_string(ac_name_bytes)

        self.ugc_id_field.setText(ugc_id)
        self.data_name_field.setText(data_name)
        self.ac_name_field.setText(ac_name)

        _, assemble_bytes = read_section_value(decompressed_bytes, b'Assemble')
        if assemble_bytes is not None:
            parts, weapons = process_assemble_bytes(assemble_bytes)
            if parts is not None and weapons is not None:
                for i, (equipment_id, category) in enumerate(parts):
                    match_found = False
                    for index in range(self.part_fields[i].count()):
                        if str(equipment_id) in self.part_fields[i].itemText(index):
                            self.part_fields[i].setCurrentIndex(index)
                            match_found = True
                            break
                    if not match_found:
                        self.part_fields[i].setEditText(f"{equipment_id}")

                for i, (equipment_id, category) in enumerate(weapons):
                    if i < len(self.weapon_fields):
                        match_found = False
                        for index in range(self.weapon_fields[i].count()):
                            if str(equipment_id) in self.weapon_fields[i].itemText(index):
                                self.weapon_fields[i].setCurrentIndex(index)
                                match_found = True
                                break
                        if not match_found:
                            self.weapon_fields[i].setEditText(f"{equipment_id}")
        else:
            print("Assemble section not found.")

        _, coloring_bytes = read_section_value(decompressed_bytes, b'Coloring')
        color_datas = process_coloring_bytes(coloring_bytes)
        for i in range(len(self.coloring_sections)):
            self.coloring_sections[i].import_settings(color_datas[i])

    def save_to_sl2(self):
        appdata_path = os.path.expandvars("%AppData%")
        default_dir = os.path.join(appdata_path, "ArmoredCore6")
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select Save File', default_dir, 'Save Files (*.sl2)')
        if file_path:
            # Backup the original .sl2 file
            backup_filename = f"{os.path.splitext(os.path.basename(file_path))[0]}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.sl2"
            backup_path = os.path.join(os.path.dirname(file_path), backup_filename)
            shutil.copy(file_path, backup_path)

            max_category_size = 40
            max_file_presets = 32
            with tempfile.TemporaryDirectory() as temp_dir:
                # Copy the selected .sl2 file to the temporary directory
                temp_sl2_path = os.path.join(temp_dir, os.path.basename(file_path))
                shutil.copy(file_path, temp_sl2_path)

                # Unpack the .sl2 file using run_witchy
                run_witchy(temp_sl2_path, True)

                # Find the unpacked folder
                unpacked_folder = f"{os.path.splitext(os.path.basename(file_path))[0]}-sl2"
                unpacked_path = os.path.join(temp_dir, unpacked_folder)

                # Create a subfolder for encrypted backups
                encrypted_backup_path = os.path.join(temp_dir, "encrypted_backup")
                os.mkdir(encrypted_backup_path)

                # Copy all encrypted files to the backup folder
                for root, _, files in os.walk(unpacked_path):
                    for file in files:
                        if not file.endswith(".xml"):
                            src = os.path.join(root, file)
                            dst = os.path.join(encrypted_backup_path, file)
                            shutil.copy(src, dst)

                preset_count = 99
                data = None
                current_data = 1
                while preset_count >= max_file_presets:
                    current_data += 1  # We start at USER_DATA_002
                    if current_data > 6:
                        break
                    data_path = os.path.join(unpacked_path, f"USER_DATA0{str(current_data).zfill(2)}")
                    decrypt_file(data_path)
                    with open(data_path, "rb") as file:
                        data = file.read()
                        preset_count = struct.unpack_from('<I', data, 0x10)[0]
                if current_data > 6:
                    QMessageBox.critical(None, "Error", f"You don't have any slots remaining in this save file!")
                    return

                user_data_final = UserDesignData.from_bytes(data)

                # Now we gotta figure out to which category we want to add it to.
                # Iterate over USER_DATA002-006 and collect presets by category
                presets_by_category = {i + 1: [] for i in range(4)}
                for i in range(2, 7):
                    user_data_path = os.path.join(unpacked_path, f"USER_DATA00{i}")
                    if i != current_data:
                        decrypt_file(user_data_path)
                    with open(user_data_path, "rb") as file:
                        user_data_content = file.read()
                    if i != current_data:
                        encrypt_file(user_data_path)

                    user_data = UserDesignData.from_bytes(user_data_content)
                    for preset in user_data.presets:
                        category = preset.category
                        presets_by_category[category].append(preset)

                # Find categories with less than 40 members
                categories_under_capacity = [f"Tab {category}" for category, presets in presets_by_category.items() if len(presets) < max_category_size]

                # Present a dialog for the user to choose a category
                category, ok = QInputDialog.getItem(self, "Select Tab", "Choose a tab:", categories_under_capacity, 0, False)
                if ok and category:
                    selected_category = int(category.split(" ")[1])
                else:
                    return

                thumbnail = ACThumbnail.empty_thumbnail()
                reply = QMessageBox.question(self, 'Thumbnail',
                                             'Do you want to add a thumbnail?',
                                             QMessageBox.StandardButton.Yes |
                                             QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    fname, _ = QFileDialog.getOpenFileName(None, 'Open file',
                                                           filter="Image files (*.jpg *.png *.bmp)")
                    if fname:
                        thumbnail = ACThumbnail.from_image(fname)

                new_preset = Preset(selected_category, date_time=datetime.datetime.now(), design=ASMC(self.generate_design_from_ui()),
                                    thumbnail=thumbnail)
                user_data_final.add_preset(new_preset)

                with open(os.path.join(unpacked_path, f"USER_DATA0{str(current_data).zfill(2)}"), "wb") as file:
                    file.write(user_data_final.to_bytes())

                # Encrypt only the modified file
                encrypt_file(os.path.join(unpacked_path, f"USER_DATA0{str(current_data).zfill(2)}"))

                # Copy back all other encrypted files from the backup
                for file in os.listdir(encrypted_backup_path):
                    if file != f"USER_DATA0{str(current_data).zfill(2)}":
                        src = os.path.join(encrypted_backup_path, file)
                        dst = os.path.join(unpacked_path, file)
                        shutil.copy(src, dst)

                run_witchy(unpacked_path)
                shutil.copy(temp_sl2_path, file_path)
                time.sleep(1)
            QMessageBox.information(self, "Save Complete", f"Design added to save file.")

    def generate_design_from_ui(self) -> bytes:
        end_data = None
        if self.userimage_textbox.text() != "" or self.stored_original_design:
            # Load the original file
            if self.userimage_textbox.text() != "" and os.path.exists(self.userimage_textbox.text()):
                with open(self.userimage_textbox.text(), 'rb') as file:
                    original_data = file.read()
            else:
                original_data = self.stored_original_design

            # Check if the file needs to be decompressed
            if original_data.startswith(b'ASMC'):
                original_data = self.try_decompress(original_data)
                if original_data is None:
                    raise ValueError("Decompression failed.")

            # Find the start of the "Coloring" section
            end_start = original_data.find(b'UserImage')
            if end_start == -1:
                raise ValueError("End section not found in the original file.")

            # Store everything starting at the "Coloring" section
            end_data = original_data[end_start:]

        # Create a BytesIO object to store the modified data
        modified_data = BytesIO()

        # Write the "---- begin ----" header
        begin_header = ChunkHeader('---- begin ----', 0, 0)
        modified_data.write(begin_header.to_bytes())

        # Write the UgcID section
        ugc_id = self.ugc_id_field.text()
        if ugc_id == "": ugc_id = "99999999"
        ugc_id_bytes = ugc_id.encode('utf-16-le') + b"\x00\x00"
        ugc_id_header = ChunkHeader('UgcID', len(ugc_id_bytes), 0)
        modified_data.write(ugc_id_header.to_bytes())
        modified_data.write(ugc_id_bytes)

        # Write the DataName section
        data_name = self.data_name_field.text()
        if data_name == "": data_name = "DATA_NAME"
        data_name_bytes = data_name.encode('utf-16-le') + b"\x00\x00"
        data_name_header = ChunkHeader('DataName', len(data_name_bytes), 0)
        modified_data.write(data_name_header.to_bytes())
        modified_data.write(data_name_bytes)

        # Write the AcName section
        ac_name = self.ac_name_field.text()
        if ac_name == "": ac_name = "AC_NAME"
        ac_name_bytes = ac_name.encode('utf-16-le') + b"\x00\x00"
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
            part_id = int(part_field.currentText().split(' ')[0].strip())
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
                    weapon_id = int(weapon_field.currentText().split(' ')[0].strip())
                assemble_data.write(equipment_id_to_save_id(weapon_id, 'weapon'))

        assemble_header = ChunkHeader('Assemble', len(assemble_data.getvalue()), 3)
        modified_data.write(assemble_header.to_bytes())
        modified_data.write(assemble_data.getvalue())

        # Write the color sets
        color_set_data = BytesIO()
        for i, section in enumerate(self.coloring_sections):
            section_data_bytes = section.export_settings().to_bytes()
            color_set_data.write(section_data_bytes)
            # Write dummy data for unknown sections
            if i == 4:  # After Right weapon
                for _ in range(2):
                    color_set_data.write(section_data_bytes)  # Repeat Right weapon data
            elif i == 7:  # After Left weapon
                for _ in range(3):
                    color_set_data.write(section_data_bytes)  # Repeat Left weapon data

        # Update the "Coloring" header with the actual length
        coloring_header = ChunkHeader('Coloring', len(color_set_data.getvalue()), 3)
        modified_data.write(coloring_header.to_bytes())
        # Write the color set data
        modified_data.write(color_set_data.getvalue())

        # Write the stored end data (UserImage and beyond)
        if end_data:
            modified_data.write(end_data)
            return modified_data.getvalue()
        else:
            # Create empty chunks for UserImage and ----  end  ----
            userimage_header = ChunkHeader("UserImage", 4, 0)
            modified_data.write(userimage_header.to_bytes())
            modified_data.write(b"\x00\x00\x00\x00")

            # Create Decal chunk
            decal_data = BytesIO()
            decal_slot_count = 5
            for k in range(decal_slot_count):
                decal_count = 1
                decal_data.write(struct.pack('<I', decal_count))
                for j in range(decal_count):
                    decal_data.write(struct.pack('<I', 0))  # imageId
                    decal_data.write(struct.pack('<fffffffff', 0, 0, 0, 0, 0, 0, 0, 0, 0))  # unk04 to unk24
                    decal_data.write(struct.pack('<II', 0, 0))  # unk28 and unk2c
                    decal_data.write(struct.pack('<f', 0))  # unk30
                    decal_data.write(struct.pack('<HHI', 0, 0, 0))  # unk34, unk36, unk38
                    decal_data.write(struct.pack('<BBBB', 0, 0, 0, 0))  # unk3c, unk3d, unk3e, unk3f
            decal_header = ChunkHeader('Decal', len(decal_data.getvalue()), 1)
            modified_data.write(decal_header.to_bytes())
            modified_data.write(decal_data.getvalue())

            # Create Marking chunk
            marking_data = BytesIO()
            marking_version = 2
            slot_count = 17
            decal_ids = [0] * slot_count
            use_emblem = [0] * slot_count
            marking_data.write(struct.pack(f'<{slot_count}I', *decal_ids))
            marking_data.write(struct.pack(f'<{slot_count}B', *use_emblem))
            marking_header = ChunkHeader('Marking', len(marking_data.getvalue()), marking_version)
            modified_data.write(marking_header.to_bytes())
            modified_data.write(marking_data.getvalue())

            end_header = ChunkHeader("----  end  ----", 0, 0)
            modified_data.write(end_header.to_bytes())

            return modified_data.getvalue()

    def save_design_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save File', '', 'All Files (*)')
        if file_path:
            design_data = self.generate_design_from_ui()
            # Save the modified data to the selected file path
            with open(file_path, 'wb') as file:
                file.write(design_data)

            QMessageBox.information(self, "Save Complete", f"Design file saved as {file_path}.")

def get_github_release(repo_owner, repo_name, tag=None) -> (str, list):
    if tag:
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/{tag}"
    else:
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
    response = requests.get(api_url)
    if response.status_code == 200:
        release_data = response.json()
        latest_tag = release_data["tag_name"]
        return latest_tag, release_data["assets"]
    else:
        return None



def check_tools():
    os.makedirs(TOOLS_FOLDER, exist_ok=True)

    if not os.path.exists(VERSIONS_FILE):
        with open(VERSIONS_FILE, "w") as fp:
            json.dump({}, fp)

    with open(VERSIONS_FILE, 'r') as file:
        versions = json.load(file)

    global texconv_path
    texconv_path = os.path.join(TOOLS_FOLDER, "DirectXTex", "texconv.exe")
    os.makedirs(os.path.join(TOOLS_FOLDER, "DirectXTex"), exist_ok=True)
    latest_texconv_release = get_github_release("microsoft", "DirectXTex")
    if latest_texconv_release and versions.get("texconv", "0.0") != latest_texconv_release[0]:
        DownloadDialog(f"Downloading texconv", "https://github.com/microsoft/DirectXTex/releases/latest/download/texconv.exe", texconv_path).exec()
        versions["texconv"] = latest_texconv_release[0]

    os.makedirs(witchy_dir, exist_ok=True)
    latest_witchy_release = get_github_release("ividyon", "WitchyBND")
    if latest_witchy_release and versions.get("witchy", "0.0") != latest_witchy_release[0]:
        zip_path = os.path.join(witchy_dir, "witchy.zip")
        DownloadDialog(f"Downloading WitchyBND", latest_witchy_release[1][0]["browser_download_url"], zip_path).exec()
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(witchy_dir)

        versions["witchy"] = latest_witchy_release[0]




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

    stylesheet = open(os.path.join(os.path.dirname(__file__), "resources", "stylesheet.qss")).read()

    for colorKey, colorValue in colors_dict.items():
        stylesheet = stylesheet.replace("{" + colorKey + "}", colorValue)

    app = QApplication([])

    app.setStyleSheet(stylesheet)
    check_tools()

    decompressor = DesignDecompressor()
    decompressor.show()

    app.exec()