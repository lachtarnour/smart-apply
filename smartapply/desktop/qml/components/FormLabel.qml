import QtQuick

Text {
    id: root
    property int fontPixelSize: 10
    color: Theme.inkSoft
    font.pixelSize: root.fontPixelSize
    font.weight: Font.Bold
    font.letterSpacing: 0.45
    renderType: Text.NativeRendering
}
