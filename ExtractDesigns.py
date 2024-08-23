import os
import sys
import tempfile
import shutil
from design_editor import run_witchy, decrypt_file, UserDesignData, ASMC, read_section_value, convert_to_string


def extract_designs(sl2_path, output_dir=None):
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(sl2_path), os.path.basename(sl2_path).replace(".","-") + "-design")

    os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        # Copy the .sl2 file to the temporary directory
        temp_sl2_path = os.path.join(temp_dir, os.path.basename(sl2_path))
        shutil.copy(sl2_path, temp_sl2_path)

        # Unpack the .sl2 file
        run_witchy(temp_sl2_path, True)

        # Find the unpacked folder
        unpacked_folder = f"{os.path.splitext(os.path.basename(sl2_path))[0]}-sl2"
        unpacked_path = os.path.join(temp_dir, unpacked_folder)

        # Process USER_DATA002 to USER_DATA006
        for current_data in range(2, 7):
            data_path = os.path.join(unpacked_path, f"USER_DATA0{str(current_data).zfill(2)}")
            if os.path.exists(data_path):
                decrypt_file(data_path)
                with open(data_path, "rb") as file:
                    data = file.read()
                    user_data = UserDesignData.from_bytes(data)

                    for i, preset in enumerate(user_data.presets):
                        design_bytes = preset.design.decompress()

                        _, data_name_bytes = read_section_value(design_bytes, b'DataName')
                        _, ac_name_bytes = read_section_value(design_bytes, b'AcName')

                        data_name = convert_to_string(data_name_bytes).replace(" ", "_")
                        ac_name = convert_to_string(ac_name_bytes).replace(" ", "_")

                        # Create filename
                        filename = f"{data_name}_{ac_name} - USER_DATA0{str(current_data).zfill(2)}[{i}].design"
                        filename = ''.join(c for c in filename if c.isalnum() or c in ['_', '-', "[", "]", "."])  # Sanitize filename

                        # Save the design file
                        with open(os.path.join(output_dir, filename), 'wb') as design_file:
                            design_file.write(design_bytes)

                        print(f"Extracted: {filename}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_designs.py <sl2_file> [output_directory]")
        sys.exit(1)

    sl2_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    extract_designs(sl2_path, output_dir)
    print("Extraction complete.")