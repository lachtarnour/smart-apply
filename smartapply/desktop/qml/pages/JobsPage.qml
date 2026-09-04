import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"

Item {
    id: root
    objectName: "jobsPage"
    signal navigateRequested(string route)

    property int selectedId: AppBridge.currentJob.id || 0
    property string sortKey: "score"
    property bool sortAscending: false
    property var selectedJobs: ({})
    readonly property int columnGap: 8
    readonly property int selectWidth: 28
    readonly property int companyWidth: 138
    readonly property int experienceWidth: 82
    readonly property int locationWidth: 124
    readonly property int contractWidth: 78
    readonly property int scoreWidth: 68
    readonly property int statusWidth: 112

    function companyX() { return selectWidth + columnGap }
    function titleX() { return companyX() + companyWidth + columnGap }
    function statusX(contentWidth) { return contentWidth - statusWidth }
    function scoreX(contentWidth) { return statusX(contentWidth) - columnGap - scoreWidth }
    function contractX(contentWidth) { return scoreX(contentWidth) - columnGap - contractWidth }
    function locationX(contentWidth) { return contractX(contentWidth) - columnGap - locationWidth }
    function experienceX(contentWidth) { return locationX(contentWidth) - columnGap - experienceWidth }
    function titleWidthFor(contentWidth) { return Math.max(72, experienceX(contentWidth) - columnGap - titleX()) }

    function valueFor(row, key) {
        if (key === "score") return row.score === null || row.score === undefined ? -1 : Number(row.score)
        if (key === "experience") {
            var value = String(row.experience || "")
            var match = value.match(/[0-9]+/)
            if (match) return Number(match[0])
            var ranks = {"intern": 0, "stage": 0, "entry": 1, "junior": 1, "mid": 3, "senior": 6, "lead": 8, "principal": 9}
            return ranks[value.toLowerCase()] === undefined ? -1 : ranks[value.toLowerCase()]
        }
        if (key === "status") return String(row.status_label || "").toLowerCase()
        return String(row[key] || "").toLowerCase()
    }

    function sortedRows() {
        var rows = (AppBridge.jobs || []).slice()
        rows.sort(function(a, b) {
            var left = root.valueFor(a, root.sortKey)
            var right = root.valueFor(b, root.sortKey)
            var result = 0
            if (typeof left === "number" && typeof right === "number") result = left - right
            else result = String(left).localeCompare(String(right), "fr", {sensitivity: "base"})
            if (result === 0) result = Number(a.id) - Number(b.id)
            return root.sortAscending ? result : -result
        })
        return rows
    }

    property var sortedJobs: {
        var rowsDependency = AppBridge.jobs
        var keyDependency = sortKey
        var directionDependency = sortAscending
        return sortedRows()
    }
    property var selectedRows: {
        var selectionDependency = selectedJobs
        var rows = AppBridge.jobs || []
        var result = []
        for (var i = 0; i < rows.length; ++i) {
            if (selectionDependency[String(rows[i].id)]) result.push(rows[i])
        }
        return result
    }
    property var selectedIds: selectedRows.map(function(row) { return Number(row.id) })
    property var topLabelIds: selectedRows.filter(function(row) { return row.status !== "archived" && !row.application_id }).map(function(row) { return Number(row.id) })
    property var generationIds: selectedRows.filter(function(row) { return !row.application_id && row.status !== "archived" }).map(function(row) { return Number(row.id) })
    property var rescueIds: selectedRows.filter(function(row) { return row.status === "archived" }).map(function(row) { return Number(row.id) })
    property int selectedCount: selectedIds.length
    property bool allVisibleSelected: {
        if (sortedJobs.length === 0) return false
        for (var i = 0; i < sortedJobs.length; ++i) {
            if (!selectedJobs[String(sortedJobs[i].id)]) return false
        }
        return true
    }

    function isSelected(jobId) { return Boolean(selectedJobs[String(jobId)]) }
    function setSelected(jobId, checked) {
        var next = {}
        for (var key in selectedJobs) next[key] = selectedJobs[key]
        if (checked) next[String(jobId)] = true
        else delete next[String(jobId)]
        selectedJobs = next
    }
    function clearSelection() { selectedJobs = ({}) }
    function selectAllVisible() {
        var next = {}
        for (var key in selectedJobs) next[key] = selectedJobs[key]
        for (var i = 0; i < sortedJobs.length; ++i) next[String(sortedJobs[i].id)] = true
        selectedJobs = next
    }
    function sortBy(key) {
        if (sortKey === key) sortAscending = !sortAscending
        else {
            sortKey = key
            sortAscending = key === "score" ? false : true
        }
    }
    function toneColor(tone) {
        if (tone === "success") return Theme.success
        if (tone === "warning") return Theme.warning
        if (tone === "danger") return Theme.danger
        if (tone === "accent") return Theme.accent
        return Theme.inkMuted
    }

    Timer {
        id: searchTimer
        interval: 260
        onTriggered: {
            root.clearSelection()
            AppBridge.loadJobs(searchField.text, statusFilter.currentValue || "")
        }
    }

    Connections {
        target: AppBridge
        function onJobSelectionClearRequested() { root.clearSelection() }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 14

        PageHeader {
            Layout.fillWidth: true
            eyebrow: "SUIVI DES OPPORTUNITÉS"
            title: "Offres"
            subtitle: "Comparez les opportunités, ajustez votre Top sélection et préparez les candidatures les plus pertinentes."
            AppButton {
                text: ""
                iconSource: Theme.icon("refresh")
                implicitWidth: 44
                ToolTip.visible: hovered
                ToolTip.text: "Actualiser les offres"
                onClicked: AppBridge.loadJobs(searchField.text, statusFilter.currentValue || "")
            }
            AppButton {
                text: (AppBridge.shortlist.ready_to_generate || 0) > 0
                    ? "Générer les candidatures (" + AppBridge.shortlist.ready_to_generate + ")"
                    : "Candidatures à jour"
                iconSource: Theme.icon("sparkle")
                kind: "primary"
                enabled: (AppBridge.shortlist.ready_to_generate || 0) > 0 && !AppBridge.busy
                onClicked: AppBridge.generateShortlistedApplications()
            }
        }

        Surface {
            Layout.fillWidth: true
            Layout.preferredHeight: 74
            padding: 12
            elevated: false
            surfaceColor: Theme.surfaceMuted
            surfaceEndColor: Theme.surface
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                AppField {
                    id: searchField
                    Layout.fillWidth: true
                    implicitHeight: 48
                    iconSource: Theme.icon("search")
                    placeholderText: "Rechercher une entreprise, un poste, une ville…"
                    onTextChanged: searchTimer.restart()
                }
                AppSelect {
                    id: statusFilter
                    Layout.preferredWidth: 184
                    textRole: "label"
                    valueRole: "value"
                    model: [{label: "Tous les statuts", value: ""}].concat(AppBridge.jobStatuses)
                    onActivated: {
                        root.clearSelection()
                        AppBridge.loadJobs(searchField.text, currentValue || "")
                    }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 30; color: Theme.lineStrong }
                ColumnLayout {
                    spacing: 1
                    Text { text: "TOP AUTOMATIQUE"; color: Theme.inkFaint; font.pixelSize: 8; font.weight: Font.Bold; font.letterSpacing: 0.8 }
                    Text { text: "Nombre d’offres à privilégier"; color: Theme.inkMuted; font.pixelSize: 10 }
                }
                AppSpinBox { id: topK; from: 1; to: 100; value: AppBridge.topK; Layout.preferredWidth: 116; implicitHeight: 46 }
                AppButton { text: "Appliquer"; iconSource: Theme.icon("check"); implicitHeight: 46; enabled: !AppBridge.busy; onClicked: AppBridge.updateShortlist(topK.value) }
                Rectangle {
                    Layout.preferredWidth: resultCount.implicitWidth + 22
                    Layout.preferredHeight: 32
                    radius: 16
                    color: Theme.neutralSoft
                    border.color: Theme.line
                    Text {
                        id: resultCount
                        anchors.centerIn: parent
                        text: AppBridge.jobs.length + " résultat" + (AppBridge.jobs.length === 1 ? "" : "s")
                        color: Theme.inkMuted
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                    }
                }
            }
        }

        Rectangle {
            visible: root.selectedCount > 0
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 64 : 0
            radius: 16
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "#2C2545" }
                GradientStop { position: 1; color: "#1B1825" }
            }
            border.color: Theme.accentLine
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.leftMargin: 18; anchors.rightMargin: 18; anchors.top: parent.top; height: 1; color: "#25FFFFFF" }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 10
                spacing: 10
                Rectangle {
                    Layout.preferredWidth: 38; Layout.preferredHeight: 38; radius: 12
                    color: Theme.accentSoft; border.color: Theme.accentLine
                    Text { anchors.centerIn: parent; text: root.selectedCount; color: Theme.accentDark; font.pixelSize: 13; font.weight: Font.Bold }
                }
                ColumnLayout {
                    spacing: 1
                    Text { text: root.selectedCount === 1 ? "1 offre sélectionnée" : root.selectedCount + " offres sélectionnées"; color: Theme.ink; font.pixelSize: 12; font.weight: Font.DemiBold }
                    Text { text: "Choisissez une action groupée"; color: Theme.inkMuted; font.pixelSize: 9 }
                }
                Item { Layout.fillWidth: true }
                AppButton {
                    text: "Effacer"
                    iconSource: Theme.icon("x")
                    implicitHeight: 38
                    onClicked: root.clearSelection()
                }
                AppButton {
                    visible: root.topLabelIds.length > 0
                    text: "Ajouter au Top (" + root.topLabelIds.length + ")"
                    iconSource: Theme.icon("plus")
                    implicitHeight: 38
                    enabled: root.topLabelIds.length > 0 && !AppBridge.busy
                    ToolTip.visible: hovered && root.topLabelIds.length === 0
                    ToolTip.text: "Aucune offre active à labeliser"
                    onClicked: AppBridge.labelJobsAsTop(root.topLabelIds)
                }
                AppButton {
                    visible: root.rescueIds.length > 0
                    text: "Restaurer (" + root.rescueIds.length + ")"
                    iconSource: Theme.icon("refresh")
                    implicitHeight: 38
                    enabled: root.rescueIds.length > 0 && !AppBridge.busy
                    ToolTip.visible: hovered && root.rescueIds.length === 0
                    ToolTip.text: "Aucune offre archivée dans la sélection"
                    onClicked: AppBridge.rescueJobs(root.rescueIds)
                }
                AppButton {
                    visible: root.generationIds.length > 0
                    text: "Créer les candidatures (" + root.generationIds.length + ")"
                    iconSource: Theme.icon("sparkle")
                    kind: "primary"
                    implicitHeight: 38
                    enabled: root.generationIds.length > 0 && !AppBridge.busy
                    ToolTip.visible: hovered && root.generationIds.length === 0
                    ToolTip.text: "Aucune candidature ne peut être créée pour cette sélection"
                    onClicked: AppBridge.generateApplications(root.generationIds)
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            Surface {
                id: tableSurface
                Layout.preferredWidth: Math.max(720, root.width * 0.66)
                Layout.minimumWidth: 700
                Layout.fillHeight: true
                padding: 0
                elevated: false
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 48
                            color: Theme.surfaceMuted
                            radius: Theme.radiusLarge
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 18; color: parent.color }
                            Item {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                SelectionBox {
                                    x: 0
                                    anchors.verticalCenter: parent.verticalCenter
                                    checked: root.allVisibleSelected
                                    partial: root.selectedCount > 0 && !root.allVisibleSelected
                                    onToggled: function(checked) { if (checked) root.selectAllVisible(); else root.clearSelection() }
                                }
                                SortHeader { x: root.companyX(); width: root.companyWidth; anchors.verticalCenter: parent.verticalCenter; title: "Entreprise"; sortKey: "company"; active: root.sortKey === sortKey; ascending: root.sortAscending; onSortRequested: function(key) { root.sortBy(key) } }
                                SortHeader { x: root.titleX(); width: root.titleWidthFor(parent.width); anchors.verticalCenter: parent.verticalCenter; title: "Poste"; sortKey: "title"; active: root.sortKey === sortKey; ascending: root.sortAscending; onSortRequested: function(key) { root.sortBy(key) } }
                                SortHeader { x: root.experienceX(parent.width); width: root.experienceWidth; anchors.verticalCenter: parent.verticalCenter; title: "Expérience"; sortKey: "experience"; active: root.sortKey === sortKey; ascending: root.sortAscending; onSortRequested: function(key) { root.sortBy(key) } }
                                SortHeader { x: root.locationX(parent.width); width: root.locationWidth; anchors.verticalCenter: parent.verticalCenter; title: "Lieu"; sortKey: "location"; active: root.sortKey === sortKey; ascending: root.sortAscending; onSortRequested: function(key) { root.sortBy(key) } }
                                SortHeader { x: root.contractX(parent.width); width: root.contractWidth; anchors.verticalCenter: parent.verticalCenter; title: "Contrat"; sortKey: "contract"; active: root.sortKey === sortKey; ascending: root.sortAscending; onSortRequested: function(key) { root.sortBy(key) } }
                                SortHeader { x: root.scoreX(parent.width); width: root.scoreWidth; anchors.verticalCenter: parent.verticalCenter; title: "Score"; sortKey: "score"; active: root.sortKey === sortKey; ascending: root.sortAscending; alignRight: true; onSortRequested: function(key) { root.sortBy(key) } }
                                SortHeader { x: root.statusX(parent.width); width: root.statusWidth; anchors.verticalCenter: parent.verticalCenter; title: "Statut"; sortKey: "status"; active: root.sortKey === sortKey; ascending: root.sortAscending; onSortRequested: function(key) { root.sortBy(key) } }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }

                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            EmptyState {
                                visible: AppBridge.jobs.length === 0
                                anchors.centerIn: parent
                                iconSource: Theme.icon("search")
                                title: "Aucun résultat"
                                message: "Modifiez les filtres ou lancez une recherche."
                            }
                            ListView {
                                id: jobsTable
                                anchors.fill: parent
                                anchors.margins: 7
                                visible: AppBridge.jobs.length > 0
                                clip: true
                                spacing: 4
                                reuseItems: true
                                cacheBuffer: 420
                                boundsBehavior: Flickable.StopAtBounds
                                model: root.sortedJobs
                                ScrollBar.vertical: AppScrollBar { }
                                delegate: Rectangle {
                                    required property var modelData
                                    width: jobsTable.width
                                    height: 70
                                    radius: 12
                                    color: root.selectedId === modelData.id ? Theme.accentSoft : (rowHover.hovered ? Theme.surfaceHover : "transparent")
                                    border.color: root.selectedId === modelData.id ? Theme.accentLine : "transparent"
                                    border.width: 1
                                    Rectangle {
                                        visible: root.selectedId === modelData.id
                                        anchors.left: parent.left
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 3
                                        height: 34
                                        radius: 2
                                        color: Theme.accentBright
                                    }
                                    Item {
                                        anchors.fill: parent
                                        anchors.leftMargin: 5
                                        anchors.rightMargin: 3
                                        SelectionBox {
                                            z: 2
                                            x: 0
                                            anchors.verticalCenter: parent.verticalCenter
                                            checked: root.isSelected(modelData.id)
                                            onToggled: function(checked) { root.setSelected(modelData.id, checked) }
                                        }
                                        Column {
                                            x: root.companyX(); width: root.companyWidth; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                                            Text { width: parent.width; text: modelData.company; color: Theme.ink; font.pixelSize: 11; font.weight: Font.DemiBold; elide: Text.ElideRight }
                                            Text { width: parent.width; text: modelData.source || "Source inconnue"; color: Theme.inkFaint; font.pixelSize: 8; font.capitalization: Font.AllUppercase; elide: Text.ElideRight }
                                        }
                                        Column {
                                            x: root.titleX(); width: root.titleWidthFor(parent.width); anchors.verticalCenter: parent.verticalCenter; spacing: 3
                                            Text { width: parent.width; text: modelData.title; color: Theme.inkSoft; font.pixelSize: 11; font.weight: Font.Medium; elide: Text.ElideRight }
                                            Text { width: parent.width; text: modelData.filter_disposition === "relevant" ? "Profil pertinent" : (modelData.filter_disposition === "uncertain" ? "Pertinence à confirmer" : ""); color: modelData.filter_disposition === "relevant" ? Theme.success : Theme.warning; font.pixelSize: 8; elide: Text.ElideRight }
                                        }
                                        Text { x: root.experienceX(parent.width); width: root.experienceWidth; anchors.verticalCenter: parent.verticalCenter; text: modelData.experience || "—"; color: Theme.inkMuted; font.pixelSize: 10; elide: Text.ElideRight }
                                        Text { x: root.locationX(parent.width); width: root.locationWidth; anchors.verticalCenter: parent.verticalCenter; text: modelData.location || "—"; color: Theme.inkMuted; font.pixelSize: 10; elide: Text.ElideRight }
                                        Text { x: root.contractX(parent.width); width: root.contractWidth; anchors.verticalCenter: parent.verticalCenter; text: modelData.contract || "—"; color: Theme.inkMuted; font.pixelSize: 10; elide: Text.ElideRight }
                                        Rectangle {
                                            x: root.scoreX(parent.width)
                                            width: root.scoreWidth
                                            height: 30
                                            anchors.verticalCenter: parent.verticalCenter
                                            radius: 10
                                            color: modelData.score === null || modelData.score === undefined ? "transparent" : Theme.accentSoft
                                            border.color: modelData.score === null || modelData.score === undefined ? "transparent" : Theme.accentLine
                                            Text { anchors.centerIn: parent; text: modelData.score_text; color: modelData.score === null || modelData.score === undefined ? Theme.inkFaint : Theme.accentDark; font.pixelSize: 11; font.weight: Font.Bold }
                                        }
                                        Item {
                                            x: root.statusX(parent.width)
                                            width: root.statusWidth
                                            height: 24
                                            anchors.verticalCenter: parent.verticalCenter
                                            Rectangle { x: 0; width: 7; height: 7; radius: 4; anchors.verticalCenter: parent.verticalCenter; color: root.toneColor(modelData.tone) }
                                            Text { x: 13; width: parent.width - 13; anchors.verticalCenter: parent.verticalCenter; text: modelData.shortlisted ? "Top sélection" : modelData.status_label; color: modelData.shortlisted ? Theme.accentDark : Theme.inkSoft; font.pixelSize: 9; font.weight: Font.DemiBold; elide: Text.ElideRight }
                                        }
                                    }
                                    HoverHandler { id: rowHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: AppBridge.selectJob(modelData.id) }
                                    Behavior on color { ColorAnimation { duration: 120 } }
                                }
                            }
                        }
                    }
                }
            }

            Surface {
                Layout.fillWidth: true
                Layout.minimumWidth: 320
                Layout.fillHeight: true
                padding: 22
                elevated: false
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    EmptyState {
                        visible: !AppBridge.currentJob.id
                        anchors.centerIn: parent
                        iconSource: Theme.icon("briefcase")
                        title: "Sélectionnez une offre"
                    }
                    ColumnLayout {
                        visible: Boolean(AppBridge.currentJob.id)
                        anchors.fill: parent
                        spacing: 12
                        Flickable {
                            id: detailViewport
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            contentWidth: width
                            contentHeight: detailContent.implicitHeight
                            boundsBehavior: Flickable.StopAtBounds
                            clip: true
                            ScrollBar.vertical: AppScrollBar { }

                            ColumnLayout {
                                id: detailContent
                                width: detailViewport.width - 12
                                spacing: 10
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 11
                                    Rectangle {
                                        Layout.preferredWidth: 44; Layout.preferredHeight: 44; radius: 14
                                        color: Theme.accentSoft; border.color: Theme.accentLine
                                        Text { anchors.centerIn: parent; text: String(AppBridge.currentJob.company || "•").charAt(0).toUpperCase(); color: Theme.accentDark; font.pixelSize: 15; font.weight: Font.Bold }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 2
                                        Text { Layout.fillWidth: true; text: AppBridge.currentJob.company || "Entreprise non indiquée"; color: Theme.ink; font.pixelSize: 13; font.weight: Font.DemiBold; elide: Text.ElideRight }
                                        Text { Layout.fillWidth: true; text: (AppBridge.currentJob.source || "Source inconnue") + "  ·  " + (AppBridge.currentJob.location || "Lieu non indiqué"); color: Theme.inkMuted; font.pixelSize: 9; elide: Text.ElideRight }
                                    }
                                    Rectangle {
                                        visible: AppBridge.currentJob.score !== null && AppBridge.currentJob.score !== undefined
                                        Layout.preferredWidth: 72; Layout.preferredHeight: 44; radius: 13
                                        color: Theme.accentSoft; border.color: Theme.accentLine
                                        Column {
                                            anchors.centerIn: parent; spacing: 0
                                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: AppBridge.currentJob.score_text || "—"; color: Theme.accentDark; font.pixelSize: 15; font.weight: Font.Bold }
                                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "MATCH"; color: Theme.inkFaint; font.pixelSize: 7; font.weight: Font.Bold; font.letterSpacing: 0.7 }
                                        }
                                    }
                                }
                                Text { Layout.fillWidth: true; text: AppBridge.currentJob.title || ""; color: Theme.ink; font.pixelSize: 21; font.weight: Font.Bold; lineHeight: 0.95; wrapMode: Text.WordWrap }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Pill { text: AppBridge.currentJob.status_label || ""; tone: AppBridge.currentJob.tone || "neutral"; compact: true }
                                    Pill {
                                        visible: Boolean(AppBridge.currentJob.shortlisted) && AppBridge.currentJob.status !== "shortlisted"
                                        text: "Top sélection"
                                        tone: "accent"
                                        compact: true
                                    }
                                    Item { Layout.fillWidth: true }
                                }
                                Flow {
                                    Layout.fillWidth: true; spacing: 6
                                    Repeater {
                                        model: [AppBridge.currentJob.experience || "", AppBridge.currentJob.contract || "", AppBridge.currentJob.remote || ""].filter(function(v) { return v.length > 0 && v !== "—" })
                                        delegate: Pill { required property var modelData; text: modelData; compact: true }
                                    }
                                }
                                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }
                                Rectangle {
                                    visible: (AppBridge.currentJob.match_reasons || []).length > 0
                                    Layout.fillWidth: true
                                    implicitHeight: matchContent.implicitHeight + 24
                                    radius: 14
                                    color: Theme.successSoft
                                    border.color: "#285B4D"
                                    ColumnLayout {
                                        id: matchContent
                                        anchors.fill: parent; anchors.margins: 12; spacing: 7
                                        RowLayout {
                                            Layout.fillWidth: true; spacing: 7
                                            SvgIcon { source: Theme.icon("sparkle"); color: Theme.success; Layout.preferredWidth: 15; Layout.preferredHeight: 15 }
                                            Text { text: "Correspond à votre profil"; color: Theme.success; font.pixelSize: 11; font.weight: Font.DemiBold }
                                        }
                                        Repeater {
                                            model: (AppBridge.currentJob.match_reasons || []).slice(0, 4)
                                            delegate: RowLayout {
                                                required property var modelData
                                                Layout.fillWidth: true; spacing: 7
                                                Rectangle { Layout.preferredWidth: 5; Layout.preferredHeight: 5; radius: 3; color: Theme.success }
                                                Text { Layout.fillWidth: true; text: modelData; color: Theme.inkSoft; font.pixelSize: 10; wrapMode: Text.WordWrap; lineHeight: 1.18 }
                                            }
                                        }
                                    }
                                }
                                Rectangle {
                                    visible: AppBridge.currentJob.status === "archived" && (AppBridge.currentJob.archive_reasons || []).length > 0
                                    Layout.fillWidth: true
                                    implicitHeight: archiveContent.implicitHeight + 24
                                    radius: 14; color: Theme.warningSoft; border.color: "#594326"
                                    ColumnLayout {
                                        id: archiveContent
                                        anchors.fill: parent; anchors.margins: 12; spacing: 6
                                        Text { text: "Raison de l’archivage"; color: Theme.warning; font.pixelSize: 11; font.weight: Font.DemiBold }
                                        Text { Layout.fillWidth: true; text: "• " + (AppBridge.currentJob.archive_reasons || []).slice(0, 4).join("\n• "); color: Theme.inkSoft; font.pixelSize: 10; wrapMode: Text.WordWrap; lineHeight: 1.18 }
                                    }
                                }
                                Rectangle {
                                    visible: AppBridge.currentJob.status !== "archived" && (AppBridge.currentJob.risks || []).length > 0
                                    Layout.fillWidth: true
                                    implicitHeight: risksContent.implicitHeight + 24
                                    radius: 14; color: Theme.warningSoft; border.color: "#594326"
                                    ColumnLayout {
                                        id: risksContent
                                        anchors.fill: parent; anchors.margins: 12; spacing: 7
                                        RowLayout {
                                            Layout.fillWidth: true; spacing: 7
                                            SvgIcon { source: Theme.icon("alert-circle"); color: Theme.warning; Layout.preferredWidth: 15; Layout.preferredHeight: 15 }
                                            Text { text: "Points à vérifier"; color: Theme.warning; font.pixelSize: 11; font.weight: Font.DemiBold }
                                        }
                                        Text { Layout.fillWidth: true; text: "• " + (AppBridge.currentJob.risks || []).slice(0, 4).join("\n• "); color: Theme.inkSoft; font.pixelSize: 10; wrapMode: Text.WordWrap; lineHeight: 1.18 }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    FormLabel { text: "DESCRIPTION DU POSTE" }
                                    Item { Layout.fillWidth: true }
                                    Text { text: AppBridge.currentJob.role_type || AppBridge.currentJob.domain || ""; color: Theme.inkFaint; font.pixelSize: 9; elide: Text.ElideRight }
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Math.max(180, descriptionText.implicitHeight + 30)
                                    radius: Theme.radiusMedium
                                    color: Theme.surfaceMuted
                                    border.color: Theme.line
                                    Text {
                                        id: descriptionText
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.margins: 15
                                        text: AppBridge.currentJob.description || "Description indisponible"
                                        color: Theme.inkSoft
                                        font.pixelSize: 11
                                        wrapMode: Text.WordWrap
                                        lineHeight: 1.28
                                        textFormat: Text.PlainText
                                    }
                                }
                                Item { Layout.preferredHeight: 1 }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.line }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                AppButton {
                                    Layout.fillWidth: true
                                    text: Boolean(AppBridge.currentJob.application_id) ? "Ouvrir la candidature"
                                        : AppBridge.currentJob.status === "archived" ? "Restaurer l’offre"
                                        : AppBridge.currentJob.status === "analyzed" ? "Créer la candidature"
                                        : "Analyser l’offre"
                                    iconSource: Boolean(AppBridge.currentJob.application_id) ? Theme.icon("chevron-right")
                                        : AppBridge.currentJob.status === "archived" ? Theme.icon("refresh")
                                        : Theme.icon("sparkle")
                                    kind: "primary"
                                    implicitHeight: 42
                                    onClicked: {
                                        if (AppBridge.currentJob.application_id) AppBridge.openApplication(AppBridge.currentJob.application_id)
                                        else if (AppBridge.currentJob.status === "archived") AppBridge.rescueJob(AppBridge.currentJob.id)
                                        else if (AppBridge.currentJob.status === "analyzed") AppBridge.generateApplication(AppBridge.currentJob.id)
                                        else AppBridge.analyzeJob(AppBridge.currentJob.id)
                                    }
                                }
                                AppButton {
                                    visible: Boolean(AppBridge.currentJob.url)
                                    text: ""
                                    iconSource: Theme.icon("arrow-up-right")
                                    implicitWidth: 44; implicitHeight: 42
                                    ToolTip.visible: hovered
                                    ToolTip.text: "Voir l’offre originale"
                                    onClicked: AppBridge.openUrl(AppBridge.currentJob.url)
                                }
                            }
                            RowLayout {
                                visible: AppBridge.currentJob.status !== "archived" && !AppBridge.currentJob.application_id
                                Layout.fillWidth: true
                                spacing: 8
                                AppButton {
                                    Layout.fillWidth: true
                                    text: Boolean(AppBridge.currentJob.shortlisted) ? "Retirer du Top" : "Ajouter au Top"
                                    iconSource: Boolean(AppBridge.currentJob.shortlisted) ? Theme.icon("x") : Theme.icon("plus")
                                    implicitHeight: 38
                                    onClicked: AppBridge.setJobShortlisted(AppBridge.currentJob.id, !Boolean(AppBridge.currentJob.shortlisted))
                                }
                                AppButton { text: "Archiver"; kind: "danger"; implicitHeight: 38; onClicked: archiveDialog.open() }
                            }
                        }
                    }
                }
            }
        }
    }

    ConfirmDialog {
        id: archiveDialog
        anchors.centerIn: parent
        heading: "Archiver cette offre ?"
        message: "L’offre sera retirée de la liste active. Vous pourrez la restaurer ultérieurement."
        confirmText: "Archiver"
        kind: "danger"
        onAccepted: AppBridge.archiveJob(AppBridge.currentJob.id)
    }
}
