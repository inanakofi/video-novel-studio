"""Locate the current source of exports whose reports retain historical paths."""
from pathlib import Path, PurePosixPath


def export_source(report, workspace: Path) -> Path:
    source = report['source']
    if not isinstance(source, str) or not source:
        raise ValueError('Export report needs a source path.')
    # Resolve the stable workspace layout before consulting the original path:
    # the original checkout may still exist after this copy has been edited.
    parts = PurePosixPath(source.replace('\\', '/')).parts
    if len(parts) >= 5 and parts[-5] == 'stories' and parts[-3] == 'episodes' and parts[-1] == 'scenes.json':
        candidate = workspace.joinpath(*parts[-5:]).resolve()
        if candidate.is_relative_to(workspace.resolve()) and candidate.is_file():
            return candidate
    return Path(source)
