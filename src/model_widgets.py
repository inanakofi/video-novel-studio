"""Searchable model IDs, filtered by the selected task's output capability."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QCompleter

from .connections.models import filter_models


def model_picker():
    picker = QComboBox()
    picker.setEditable(True)
    picker.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    picker.lineEdit().setPlaceholderText('Search or enter a model ID')
    picker.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    picker.completer().setFilterMode(Qt.MatchFlag.MatchContains)
    picker.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    picker.setMinimumContentsLength(22)
    picker.setMaxVisibleItems(20)
    picker.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    return picker


def fill_models(picker, connection, catalog, kind=None, *, free=False, open_weights=False, selected=''):
    picker.blockSignals(True)
    picker.clear()
    picker.addItem('')
    records = filter_models(catalog.records(connection), kind, free=free, open_weights=open_weights) if connection else []
    for record in sorted(records, key=lambda r: (not r.get('free'), r['id'])):
        picker.addItem(record['id'])
        flags = [record.get('name', record['id']),
                 'Outputs: ' + ', '.join(record['output_modalities']) if record.get('modalities_known', True)
                 else 'Capabilities not reported; check compatibility with this task.']
        if record.get('free'):
            flags.append('Free according to the discovered catalog')
        if record.get('open_weights'):
            flags.append('Open weights listed by the platform; check the model license')
        picker.setItemData(picker.count() - 1, '\n'.join(flags), Qt.ItemDataRole.ToolTipRole)
    picker.setEditText(selected)
    picker.lineEdit().setPlaceholderText('Default: ' + connection.model if connection and connection.model else 'Search or enter a model ID')
    picker.setEnabled(connection is not None)
    total = len(filter_models(catalog.records(connection), kind)) if connection else 0
    picker.setToolTip(f'{len(records)} of {total} models shown. Search or enter an ID. Blank uses the default.')
    picker.blockSignals(False)
    return len(records)
