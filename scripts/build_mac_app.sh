#!/bin/zsh
set -eu
cd "${0:A:h:h}"
export CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache"
export SWIFT_MODULECACHE_PATH="$PWD/.build/ModuleCache"
# SwiftPM's linker can stamp the deployment target as the SDK version.
# Keep macOS 14 as the minimum, but opt into the installed SDK's native appearance.
mac_sdk_version=$(xcrun --sdk macosx --show-sdk-version)
build_configuration=${BUILD_CONFIGURATION:-release}
swift build --configuration "$build_configuration" --disable-sandbox --cache-path "$PWD/.build/cache" --product StoicImporterApp \
  -Xlinker -platform_version -Xlinker macos -Xlinker 14.0 -Xlinker "$mac_sdk_version"
binary_dir=$(swift build --configuration "$build_configuration" --disable-sandbox --cache-path "$PWD/.build/cache" --show-bin-path)
app="$PWD/dist/StoicImporter.app"
zsh scripts/build_app_icon.sh
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$PWD/Resources/AppIcon.icns" "$app/Contents/Resources/AppIcon.icns"
cp "$binary_dir/StoicImporterApp" "$app/Contents/MacOS/StoicImporterApp"
cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>StoicImporterApp</string>
<key>CFBundleIdentifier</key><string>org.stoicimporter.mac</string>
<key>CFBundleName</key><string>Stoic Importer</string>
<key>CFBundleDisplayName</key><string>Stoic Importer</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.1.0</string>
<key>CFBundleVersion</key><string>2</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --sign - "$app"
# Notify Finder and Launch Services after replacing an existing bundle's icon.
touch "$app"
lsregister="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [[ -x "$lsregister" ]]; then
  "$lsregister" -f "$app" || print -u2 "Warning: could not refresh app registration."
fi
print "Built: $app"
