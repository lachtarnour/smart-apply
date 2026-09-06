import QtQuick
import QtQuick.Controls

SpinBox {
    id: root
    signal userValueModified(int value)
    property int fontPixelSize: 13
    property int indicatorSize: 15
    property int indicatorWidth: 34
    property int indicatorMargin: 5
    implicitHeight: Theme.controlHeight
    implicitWidth: 132
    editable: true
    Accessible.name: "Nombre de résultats"
    leftPadding: 42
    rightPadding: 42

    function syncInputText() {
        var formatted = root.textFromValue(root.value, root.locale)
        if (spinInput.text !== formatted)
            spinInput.text = formatted
    }

    function setUserValue(candidate) {
        var normalized = Math.max(root.from, Math.min(root.to, Math.round(candidate)))
        if (normalized === root.value) {
            root.syncInputText()
            return
        }
        root.value = normalized
        root.syncInputText()
        root.userValueModified(root.value)
    }

    function commitInput() {
        var candidate = spinInput.text.trim()
        if (candidate.length === 0) {
            root.syncInputText()
            return
        }
        var parsed = Number(candidate)
        if (!isFinite(parsed)) {
            root.syncInputText()
            return
        }
        root.setUserValue(parsed)
        root.syncInputText()
    }

    onValueChanged: root.syncInputText()

    contentItem: TextInput {
        id: spinInput
        z: 2
        objectName: "spinInput"
        text: root.textFromValue(root.value, root.locale)
        color: Theme.ink
        selectionColor: "#6556B98A"
        selectedTextColor: Theme.ink
        font.pixelSize: root.fontPixelSize
        font.weight: Font.DemiBold
        horizontalAlignment: Qt.AlignHCenter
        verticalAlignment: Qt.AlignVCenter
        readOnly: !root.editable
        validator: root.validator
        inputMethodHints: Qt.ImhFormattedNumbersOnly
        selectByMouse: true
        onEditingFinished: root.commitInput()
        Keys.onReturnPressed: {
            root.commitInput()
            root.focus = false
        }
        Keys.onEnterPressed: {
            root.commitInput()
            root.focus = false
        }
        Keys.onEscapePressed: {
            root.syncInputText()
            root.focus = false
        }
    }

    up.indicator: Rectangle {
        z: 3
        x: root.width - width - root.indicatorMargin
        y: root.indicatorMargin
        width: root.indicatorWidth; height: root.height - (root.indicatorMargin * 2)
        radius: 9
        color: root.up.pressed ? Theme.surfacePressed : (upHover.hovered ? Theme.surfaceHover : "transparent")
        SvgIcon { anchors.centerIn: parent; source: Theme.icon("plus"); color: root.enabled ? Theme.inkSoft : Theme.inkFaint; width: root.indicatorSize; height: root.indicatorSize }
        HoverHandler { id: upHover }
        MouseArea {
            anchors.fill: parent
            enabled: root.enabled
            acceptedButtons: Qt.LeftButton
            onClicked: root.setUserValue(root.value + root.stepSize)
            cursorShape: Qt.PointingHandCursor
        }
    }
    down.indicator: Rectangle {
        z: 3
        x: root.indicatorMargin; y: root.indicatorMargin
        width: root.indicatorWidth; height: root.height - (root.indicatorMargin * 2)
        radius: 9
        color: root.down.pressed ? Theme.surfacePressed : (downHover.hovered ? Theme.surfaceHover : "transparent")
        SvgIcon { anchors.centerIn: parent; source: Theme.icon("minus"); color: root.enabled ? Theme.inkSoft : Theme.inkFaint; width: root.indicatorSize; height: root.indicatorSize }
        HoverHandler { id: downHover }
        MouseArea {
            anchors.fill: parent
            enabled: root.enabled
            acceptedButtons: Qt.LeftButton
            onClicked: root.setUserValue(root.value - root.stepSize)
            cursorShape: Qt.PointingHandCursor
        }
    }
    background: Rectangle {
        radius: Theme.radiusMedium
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0; color: Theme.surfaceMuted }
            GradientStop { position: 1; color: Theme.surface }
        }
        border.color: root.activeFocus ? Theme.accent : Theme.line
        border.width: root.activeFocus ? Theme.lineWidthStrong : Theme.lineWidth
        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 12; anchors.rightMargin: 12; anchors.top: parent.top; height: Theme.lineWidth; color: Theme.highlight }
    }
}
