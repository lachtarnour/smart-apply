import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"
import "pages"

ApplicationWindow {
    id: window
    width: 1480
    height: 920
    minimumWidth: 1200
    minimumHeight: 780
    visible: true
    title: "Élan"
    color: Theme.canvas
    font.family: Theme.fontFamily

    property string currentRoute: "dashboard"
    property string pendingRoute: "dashboard"
    property real pageOffset: 0
    property bool dashboardLoaded: true
    property bool searchLoaded: false
    property bool jobsLoaded: false
    property bool applicationsLoaded: false
    property bool manualLoaded: false
    property bool profileLoaded: false
    property bool settingsLoaded: false
    readonly property bool expandedNavigation: width >= 1380
    property var actions: [
        {title: "Accueil", icon: Theme.icon("home"), route: "dashboard"},
        {title: "Recherche", icon: Theme.icon("search"), route: "search"},
        {title: "Offres", icon: Theme.icon("briefcase"), route: "jobs"},
        {title: "Candidatures", icon: Theme.icon("files"), route: "applications"},
        {title: "Ajouter une offre", icon: Theme.icon("plus"), route: "manual"},
        {title: "Profil", icon: Theme.icon("user"), route: "profile"},
        {title: "Réglages", icon: Theme.icon("settings"), route: "settings"}
    ]

    function routeIndex(route) {
        var routes = ["dashboard", "search", "jobs", "applications", "manual", "profile", "settings"]
        var value = routes.indexOf(route)
        return value < 0 ? 0 : value
    }

    function refreshRoute(route) {
        if (route === "dashboard") AppBridge.refreshDashboard()
        if (route === "jobs") AppBridge.loadJobs("", "")
        if (route === "applications") AppBridge.loadApplications("", "")
        if (route === "profile") AppBridge.refreshProfile()
        if (route === "settings") AppBridge.refreshDiagnostics()
    }

    function ensureRouteLoaded(route) {
        if (route === "dashboard") dashboardLoaded = true
        else if (route === "search") searchLoaded = true
        else if (route === "jobs") jobsLoaded = true
        else if (route === "applications") applicationsLoaded = true
        else if (route === "manual") manualLoaded = true
        else if (route === "profile") profileLoaded = true
        else if (route === "settings") settingsLoaded = true
    }

    function navigate(route) {
        if (pageSwitch.running && pendingRoute === route) return
        if (route === currentRoute) {
            refreshRoute(route)
            return
        }
        pendingRoute = route
        pageSwitch.restart()
    }

    Timer {
        id: pageWarmup
        property int step: 0
        property var routes: ["search", "jobs", "applications", "manual", "profile", "settings"]
        interval: step === 0 ? 850 : 180
        repeat: true
        running: window.visible && step < routes.length
        onTriggered: {
            if (AppBridge.busy) return
            window.ensureRouteLoaded(routes[step])
            step += 1
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: navigationRail
            Layout.preferredWidth: window.expandedNavigation ? 220 : 84
            Layout.fillHeight: true
            clip: true
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0; color: Theme.chrome }
                GradientStop { position: 0.46; color: "#0B0A11" }
                GradientStop { position: 1; color: Theme.rail }
            }

            Rectangle {
                width: 280; height: 280; radius: 140
                x: navigationRail.width - 170; y: -190
                color: "#126B52FF"
            }
            Rectangle {
                width: 220; height: 220; radius: 110
                x: -150; y: navigationRail.height - 120
                color: "#0A735CFF"
            }

            Rectangle {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                width: 1
                color: Theme.line
            }

            Behavior on Layout.preferredWidth { NumberAnimation { duration: 190; easing.type: Easing.OutCubic } }

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                anchors.topMargin: 18
                anchors.bottomMargin: 16
                spacing: 5

                RowLayout {
                    Layout.fillWidth: true
                    Layout.bottomMargin: 17
                    spacing: 11
                    Item {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 46
                        Layout.preferredHeight: 46
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: 3
                            radius: 15
                            color: "#1D765CFF"
                        }
                        Image {
                            anchors.fill: parent
                            source: Qt.resolvedUrl("../resources/app_icon.svg")
                            smooth: true
                            mipmap: true
                        }
                    }
                    ColumnLayout {
                        visible: window.expandedNavigation
                        Layout.fillWidth: true
                        spacing: 0
                        Text { text: "Élan"; color: Theme.ink; font.family: Theme.fontFamily; font.pixelSize: 16; font.weight: Font.Bold; font.letterSpacing: -0.35 }
                    }
                }

                RailItem { Layout.fillWidth: window.expandedNavigation; Layout.alignment: Qt.AlignHCenter; expanded: window.expandedNavigation; text: "Accueil"; compactText: "Accueil"; iconSource: Theme.icon("home"); selected: window.currentRoute === "dashboard"; onClicked: window.navigate("dashboard") }
                RailItem { Layout.fillWidth: window.expandedNavigation; Layout.alignment: Qt.AlignHCenter; expanded: window.expandedNavigation; text: "Recherche"; compactText: "Recherche"; iconSource: Theme.icon("search"); selected: window.currentRoute === "search"; onClicked: window.navigate("search") }
                RailItem { Layout.fillWidth: window.expandedNavigation; Layout.alignment: Qt.AlignHCenter; expanded: window.expandedNavigation; text: "Offres"; compactText: "Offres"; iconSource: Theme.icon("briefcase"); selected: window.currentRoute === "jobs"; onClicked: window.navigate("jobs") }
                RailItem { Layout.fillWidth: window.expandedNavigation; Layout.alignment: Qt.AlignHCenter; expanded: window.expandedNavigation; text: "Candidatures"; compactText: "Suivi"; iconSource: Theme.icon("files"); selected: window.currentRoute === "applications"; onClicked: window.navigate("applications") }
                RailItem { Layout.fillWidth: window.expandedNavigation; Layout.alignment: Qt.AlignHCenter; expanded: window.expandedNavigation; text: "Ajouter une offre"; compactText: "Ajouter"; iconSource: Theme.icon("plus"); selected: window.currentRoute === "manual"; onClicked: window.navigate("manual") }

                Item { Layout.fillHeight: true }

                RailItem { Layout.fillWidth: window.expandedNavigation; Layout.alignment: Qt.AlignHCenter; expanded: window.expandedNavigation; text: "Profil"; compactText: "Profil"; iconSource: Theme.icon("user"); selected: window.currentRoute === "profile"; onClicked: window.navigate("profile") }
                RailItem { Layout.fillWidth: window.expandedNavigation; Layout.alignment: Qt.AlignHCenter; expanded: window.expandedNavigation; text: "Réglages"; compactText: "Réglages"; iconSource: Theme.icon("settings"); selected: window.currentRoute === "settings"; onClicked: window.navigate("settings") }
                Rectangle {
                    Layout.fillWidth: window.expandedNavigation
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: 8
                    Layout.preferredWidth: window.expandedNavigation ? 196 : 38
                    Layout.preferredHeight: window.expandedNavigation ? 48 : 38
                    radius: window.expandedNavigation ? 13 : 12
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: avatarHover.hovered ? "#302B40" : "#25222F" }
                        GradientStop { position: 1; color: avatarHover.hovered ? "#24212D" : "#1B1A21" }
                    }
                    border.color: avatarHover.hovered ? Theme.accentLine : Theme.lineStrong
                    Rectangle {
                        width: 32; height: 32; radius: 10
                        x: window.expandedNavigation ? 9 : 3
                        anchors.verticalCenter: parent.verticalCenter
                        color: Theme.accentSoft
                        border.color: Theme.accentLine
                        Text { anchors.centerIn: parent; text: AppBridge.profile.initials || "É"; color: Theme.accentBright; font.pixelSize: 10; font.weight: Font.Bold }
                    }
                    Column {
                        visible: window.expandedNavigation
                        x: 52
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 62
                        spacing: 0
                        Text { width: parent.width; text: AppBridge.profile.name || "Votre profil"; color: "#E7E5EC"; font.pixelSize: 11; font.weight: Font.DemiBold; elide: Text.ElideRight }
                    }
                    ToolTip.visible: avatarHover.hovered && !window.expandedNavigation
                    ToolTip.text: AppBridge.profile.name || "Profil"
                    HoverHandler { id: avatarHover }
                    TapHandler { onTapped: window.navigate("profile") }
                }
            }
        }

        Rectangle {
            Layout.preferredWidth: 1
            Layout.fillHeight: true
                color: Theme.line
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 60
                gradient: Gradient {
                    orientation: Gradient.Vertical
                    GradientStop { position: 0; color: "#121019" }
                    GradientStop { position: 1; color: Theme.chrome }
                }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 24
                    anchors.rightMargin: 30
                    spacing: 16
                    Item { Layout.fillWidth: true }
                    Button {
                        id: commandButton
                        Layout.preferredWidth: 220
                        Layout.preferredHeight: 36
                        hoverEnabled: true
                        onClicked: commandPalette.open()
                        contentItem: RowLayout {
                            spacing: 8
                            Rectangle {
                                Layout.preferredWidth: 24; Layout.preferredHeight: 24; radius: 8
                                color: commandButton.hovered ? Theme.accentSoft : Theme.neutralSoft
                                SvgIcon { anchors.centerIn: parent; source: Theme.icon("search"); color: commandButton.hovered ? Theme.accentBright : Theme.inkMuted; width: 13; height: 13 }
                            }
                            Text { Layout.fillWidth: true; text: "Navigation"; color: commandButton.hovered ? Theme.inkSoft : Theme.inkMuted; font.pixelSize: 11; font.weight: Font.Medium }
                        }
                        background: Rectangle {
                            radius: 12
                            gradient: Gradient {
                                orientation: Gradient.Vertical
                                GradientStop { position: 0; color: commandButton.hovered ? Theme.surfaceRaised : Theme.surfaceMuted }
                                GradientStop { position: 1; color: Theme.surface }
                            }
                            border.color: commandButton.hovered ? Theme.accentLine : Theme.line
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 12; anchors.rightMargin: 12; anchors.top: parent.top; height: 1; color: Theme.highlight }
                        }
                    }
                    Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 24; color: Theme.line }
                    RowLayout {
                        spacing: 8
                        Rectangle {
                            Layout.preferredWidth: 8; Layout.preferredHeight: 8; radius: 4
                            color: AppBridge.busy ? Theme.warning : Theme.success
                            Rectangle { anchors.centerIn: parent; width: 16; height: 16; radius: 8; color: AppBridge.busy ? "#22EDB767" : "#2455D3AA"; z: -1 }
                        }
                        Text { text: AppBridge.busy ? "Traitement" : "À jour"; color: Theme.inkMuted; font.pixelSize: 11; font.weight: Font.Medium }
                    }
                }
                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: Theme.line }
            }

            Item {
                id: contentHost
                Layout.fillWidth: true
                Layout.fillHeight: true
                opacity: 1
                scale: 1
                transform: Translate { x: window.pageOffset }
                AmbientBackdrop { anchors.fill: parent }
                StackLayout {
                    id: pages
                    anchors.fill: parent
                    anchors.leftMargin: 28
                    anchors.rightMargin: 28
                    anchors.topMargin: 12
                    anchors.bottomMargin: 20
                    currentIndex: 0
                    Loader {
                        active: window.dashboardLoaded
                        sourceComponent: Component { DashboardPage { onNavigateRequested: function(route) { window.navigate(route) } } }
                    }
                    Loader {
                        active: window.searchLoaded
                        sourceComponent: Component { SearchPage { onNavigateRequested: function(route) { window.navigate(route) } } }
                    }
                    Loader {
                        active: window.jobsLoaded
                        sourceComponent: Component { JobsPage { onNavigateRequested: function(route) { window.navigate(route) } } }
                    }
                    Loader {
                        active: window.applicationsLoaded
                        sourceComponent: Component { ApplicationsPage { onNavigateRequested: function(route) { window.navigate(route) } } }
                    }
                    Loader {
                        active: window.manualLoaded
                        sourceComponent: Component { ManualPage { onNavigateRequested: function(route) { window.navigate(route) } } }
                    }
                    Loader {
                        active: window.profileLoaded
                        sourceComponent: Component { ProfilePage { onNavigateRequested: function(route) { window.navigate(route) } } }
                    }
                    Loader {
                        active: window.settingsLoaded
                        sourceComponent: Component { SettingsPage { onNavigateRequested: function(route) { window.navigate(route) } } }
                    }
                }
            }
        }
    }

    SequentialAnimation {
        id: pageSwitch
        ParallelAnimation {
            NumberAnimation { target: contentHost; property: "opacity"; to: 0; duration: 55; easing.type: Easing.InQuad }
            NumberAnimation { target: window; property: "pageOffset"; to: -4; duration: 60; easing.type: Easing.InQuad }
        }
        ParallelAnimation {
            ScriptAction {
                script: {
                    window.ensureRouteLoaded(window.pendingRoute)
                    window.currentRoute = window.pendingRoute
                    pages.currentIndex = window.routeIndex(window.pendingRoute)
                    window.refreshRoute(window.pendingRoute)
                    window.pageOffset = 8
                }
            }
            NumberAnimation { target: contentHost; property: "opacity"; from: 0; to: 1; duration: 175; easing.type: Easing.OutCubic }
            NumberAnimation { target: window; property: "pageOffset"; from: 8; to: 0; duration: 195; easing.type: Easing.OutCubic }
        }
    }

    Popup {
        id: commandPalette
        width: Math.min(640, window.width - 80)
        height: Math.min(520, window.height - 100)
        x: Math.round((window.width - width) / 2)
        y: 78
        z: 100
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onOpened: { commandSearch.text = ""; commandSearch.forceActiveFocus() }
        background: Item {
            Rectangle { anchors.fill: parent; anchors.topMargin: 12; anchors.bottomMargin: -12; radius: 26; color: "#85000000" }
            Rectangle {
                anchors.fill: parent
                radius: 24
                gradient: Gradient {
                    orientation: Gradient.Vertical
                    GradientStop { position: 0; color: Theme.surfaceRaised }
                    GradientStop { position: 1; color: Theme.surface }
                }
                border.color: Theme.accentLine
                border.width: 1
                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 24; anchors.rightMargin: 24; anchors.top: parent.top; height: 1; color: "#28FFFFFF" }
            }
        }
        Overlay.modal: Rectangle { color: Theme.scrim }
        contentItem: ColumnLayout {
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 68
                Layout.leftMargin: 20; Layout.rightMargin: 20
                spacing: 12
                SvgIcon { source: Theme.icon("search"); color: Theme.accent; Layout.preferredWidth: 21; Layout.preferredHeight: 21 }
                TextField {
                    id: commandSearch
                    Layout.fillWidth: true
                    placeholderText: "Rechercher une page…"
                    color: Theme.ink
                    placeholderTextColor: Theme.inkMuted
                    font.pixelSize: 16
                    background: null
                    onTextChanged: commandList.currentIndex = commandList.count > 0 ? 0 : -1
                    Keys.onDownPressed: commandList.incrementCurrentIndex()
                    Keys.onUpPressed: commandList.decrementCurrentIndex()
                    Keys.onReturnPressed: {
                        if (commandList.currentIndex >= 0 && commandList.currentIndex < commandList.count) {
                            var action = commandList.model[commandList.currentIndex]
                            window.navigate(action.route)
                            commandPalette.close()
                        }
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }
            ListView {
                id: commandList
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 10; Layout.rightMargin: 10; Layout.topMargin: 10; Layout.bottomMargin: 12
                clip: true
                spacing: 3
                model: window.actions.filter(function(item) { var q = commandSearch.text.toLowerCase(); return q.length === 0 || item.title.toLowerCase().indexOf(q) >= 0 })
                currentIndex: count > 0 ? 0 : -1
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: commandList.width
                    height: 48
                    radius: 12
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: commandHover.hovered || commandList.currentIndex === index ? "#3B315F" : "transparent" }
                        GradientStop { position: 1; color: commandHover.hovered || commandList.currentIndex === index ? Theme.accentSoft : "transparent" }
                    }
                    border.color: commandHover.hovered || commandList.currentIndex === index ? Theme.accentLine : "transparent"
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 12
                        Rectangle { Layout.preferredWidth: 34; Layout.preferredHeight: 34; radius: 11; color: commandHover.hovered ? Theme.accentLine : Theme.neutralSoft; SvgIcon { anchors.centerIn: parent; source: modelData.icon; color: Theme.accentDark; width: 17; height: 17 } }
                        Text { Layout.fillWidth: true; text: modelData.title; color: Theme.ink; font.pixelSize: 13; font.weight: Font.DemiBold }
                    }
                    HoverHandler { id: commandHover }
                    TapHandler { onTapped: { window.navigate(modelData.route); commandPalette.close() } }
                }
            }
        }
    }

    Rectangle {
        id: busyPill
        z: 50
        visible: opacity > 0
        opacity: AppBridge.busy ? 1 : 0
        anchors.top: parent.top
        anchors.topMargin: 76
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(430, busyRow.implicitWidth + 34)
        height: 44
        radius: 15
        color: Theme.surfaceRaised
        border.color: Theme.accentLine
        Row {
            id: busyRow
            anchors.centerIn: parent
            spacing: 10
            Item {
                width: 18; height: 18
                Rectangle { width: 6; height: 6; radius: 3; color: Theme.accentBright; anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter }
                RotationAnimation on rotation { running: AppBridge.busy; from: 0; to: 360; duration: 850; loops: Animation.Infinite }
            }
            Text { text: AppBridge.busyLabel || "Traitement en cours…"; color: "#EAE8F2"; font.pixelSize: 12; font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
        }
        Behavior on opacity { NumberAnimation { duration: 180 } }
    }

    Rectangle {
        id: toast
        z: 120
        property string kind: "neutral"
        property string titleText: ""
        property string messageText: ""
        anchors.right: parent.right
        anchors.rightMargin: 24
        anchors.bottom: parent.bottom
        // Keep the toast above the fixed action bar used by the application detail page.
        anchors.bottomMargin: 92
        width: 390
        implicitHeight: toastRow.implicitHeight + 28
        radius: 18
        color: Theme.surfaceRaised
        border.color: kind === "success" ? "#286B57" : kind === "danger" ? "#7E3443" : kind === "warning" ? "#785827" : "#393548"
        opacity: 0
        visible: opacity > 0
        transform: Translate { id: toastTranslate; x: 20; Behavior on x { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } } }
        RowLayout {
            id: toastRow
            anchors.fill: parent; anchors.margins: 14; spacing: 12
            Rectangle {
                Layout.preferredWidth: 38; Layout.preferredHeight: 38; radius: 12
                color: toast.kind === "success" ? "#203F36" : toast.kind === "danger" ? "#45262E" : toast.kind === "warning" ? "#443622" : "#302B4B"
                Text { anchors.centerIn: parent; text: toast.kind === "success" ? "✓" : toast.kind === "danger" ? "×" : toast.kind === "warning" ? "!" : "i"; color: toast.kind === "success" ? "#62D6B0" : toast.kind === "danger" ? "#FF8CA0" : toast.kind === "warning" ? "#F4BB62" : "#A99FFF"; font.pixelSize: 17; font.weight: Font.Bold }
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 2
                Text { Layout.fillWidth: true; text: toast.titleText; color: "#F5F3F8"; font.pixelSize: 13; font.weight: Font.DemiBold; wrapMode: Text.WordWrap }
                Text { visible: toast.messageText.length > 0; Layout.fillWidth: true; text: toast.messageText; color: "#A9A6B2"; font.pixelSize: 11; wrapMode: Text.WordWrap }
            }
        }
        Behavior on opacity { NumberAnimation { duration: 180 } }
        Timer { id: toastTimer; interval: 4600; onTriggered: { toast.opacity = 0; toastTranslate.x = 20 } }
        function show(title, message, type) { titleText = title; messageText = message; kind = type; opacity = 1; toastTranslate.x = 0; toastTimer.restart() }
    }

    Connections {
        target: AppBridge
        function onToastRequested(title, message, kind) { toast.show(title, message, kind) }
        function onNavigationRequested(route, selectedId) { window.navigate(route) }
    }

}
