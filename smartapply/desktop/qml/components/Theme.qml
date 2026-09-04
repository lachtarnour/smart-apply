pragma Singleton
import QtQuick

QtObject {
    readonly property bool darkMode: true
    readonly property string fontFamily: ".AppleSystemUIFont"
    readonly property color canvas: "#09080F"
    readonly property color canvasLift: "#100E19"
    readonly property color chrome: "#0E0D14"
    readonly property color rail: "#07070C"
    readonly property color surface: "#16141F"
    readonly property color surfaceMuted: "#1B1925"
    readonly property color surfaceRaised: "#211E2D"
    readonly property color surfaceHover: "#272333"
    readonly property color surfacePressed: "#302A40"

    readonly property color ink: "#FCFAFF"
    readonly property color inkSoft: "#E0DCE9"
    readonly property color inkMuted: "#9B96A8"
    readonly property color inkFaint: "#696476"

    readonly property color line: "#2C2939"
    readonly property color lineStrong: "#484258"
    readonly property color accent: "#8E7CFF"
    readonly property color accentBright: "#B9AEFF"
    readonly property color accentDark: "#C8C0FF"
    readonly property color accentDeep: "#6555E8"
    readonly property color accentSoft: "#2B2448"
    readonly property color accentLine: "#5D518B"
    readonly property color accentGlow: "#765FFF"
    readonly property color success: "#55D3AA"
    readonly property color successSoft: "#173930"
    readonly property color warning: "#EDB767"
    readonly property color warningSoft: "#3C2E1D"
    readonly property color danger: "#FF7F96"
    readonly property color dangerSoft: "#40232D"
    readonly property color blue: "#82AAFF"
    readonly property color neutralSoft: "#24212E"
    readonly property color highlight: "#16FFFFFF"
    readonly property color shadow: "#65000000"
    readonly property color shadowSoft: "#36000000"
    readonly property color scrim: "#B8000000"

    readonly property int radiusSmall: 10
    readonly property int radiusMedium: 14
    readonly property int radiusLarge: 20
    readonly property int radiusXLarge: 26

    readonly property int motionQuick: 90
    readonly property int motionFast: 130
    readonly property int motionMedium: 180
    readonly property int motionRelaxed: 240

    function icon(name) {
        return Qt.resolvedUrl("../../resources/icons/" + name + ".svg")
    }
}
