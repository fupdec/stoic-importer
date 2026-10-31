#!/bin/zsh
set -eu
cd "${0:A:h:h}"
iconset="$PWD/.build/AppIcon.iconset"
mkdir -p "$iconset"
for icon_size in 16 32 128 256 512; do
  sips -z "$icon_size" "$icon_size" "$PWD/Resources/AppIcon.png" --out "$iconset/icon_${icon_size}x${icon_size}.png" >/dev/null
  retina_size=$((icon_size * 2))
  sips -z "$retina_size" "$retina_size" "$PWD/Resources/AppIcon.png" --out "$iconset/icon_${icon_size}x${icon_size}@2x.png" >/dev/null
done
# PNG-backed ICNS avoids iconutil's unavailable conversion service in restricted builds.
python3 scripts/package_app_icon.py "$iconset" "$PWD/Resources/AppIcon.icns"
