"""PyInstaller hook that omits QML WebEngine modules Élan never imports."""

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml_binaries, qml_datas = pyside6_library_info.collect_qtqml_files()


def _needed(entry) -> bool:  # noqa: ANN001
    return "QtWebEngine" not in str(entry)


binaries += [entry for entry in qml_binaries if _needed(entry)]
datas += [entry for entry in qml_datas if _needed(entry)]
