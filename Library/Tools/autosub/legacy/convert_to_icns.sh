#!/bin/bash
# Script to convert PNG to ICNS
# Usage: ./convert_to_icns.sh input.png output.icns

INPUT_PNG="$1"
OUTPUT_ICNS="$2"

if [ -z "$INPUT_PNG" ] || [ -z "$OUTPUT_ICNS" ]; then
    echo "Usage: $0 input.png output.icns"
    exit 1
fi

ICONSET="tmp.iconset"
mkdir -p "$ICONSET"

# Create different sizes for the iconset
sips -z 16 16     "$INPUT_PNG" --out "$ICONSET/icon_16x16.png"
sips -z 32 32     "$INPUT_PNG" --out "$ICONSET/icon_16x16@2x.png"
sips -z 32 32     "$INPUT_PNG" --out "$ICONSET/icon_32x32.png"
sips -z 64 64     "$INPUT_PNG" --out "$ICONSET/icon_32x32@2x.png"
sips -z 128 128   "$INPUT_PNG" --out "$ICONSET/icon_128x128.png"
sips -z 256 256   "$INPUT_PNG" --out "$ICONSET/icon_128x128@2x.png"
sips -z 256 256   "$INPUT_PNG" --out "$ICONSET/icon_256x256.png"
sips -z 512 512   "$INPUT_PNG" --out "$ICONSET/icon_256x256@2x.png"
sips -z 512 512   "$INPUT_PNG" --out "$ICONSET/icon_512x512.png"
cp "$INPUT_PNG" "$ICONSET/icon_512x512@2x.png"

# Convert iconset to icns
iconutil -c icns "$ICONSET" -o "$OUTPUT_ICNS"

# Cleanup
rm -rf "$ICONSET"
