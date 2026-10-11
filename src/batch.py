"""Render multiple episodes locally and retain honest per-episode results."""
import argparse
import json
from pathlib import Path

from .media import RenderCancelled, atomic_json
from .video_renderer import render_episode


def render_batch(paths, output_directory: Path, *, cancel=None, progress=None, overrides=None):
    paths = list(paths)
    results = []
    output_directory.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(paths):
        path = Path(path)
        name = f'{path.parent.parent.parent.name}_{path.parent.name}.mp4'
        try:
            report = render_episode(path, output_directory / name, cancel=cancel, overrides=overrides,
                                    progress=(lambda value, message, i=index: progress((i + value) / len(paths), message)) if progress else None)
            results.append({'source': str(path), 'status': 'verified', 'output': report['output']})
        except RenderCancelled:
            results.append({'source': str(path), 'status': 'cancelled'})
            break
        except Exception as error:
            results.append({'source': str(path), 'status': 'failed', 'error': str(error)})
    atomic_json(output_directory / 'batch_report.json', {'results': results, 'requested': len(paths)})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('story', type=Path)
    parser.add_argument('--output', type=Path, default=Path('exports'))
    args = parser.parse_args()
    paths = sorted(args.story.glob('episodes/episode_*/scenes.json'))
    if not paths:
        parser.error('No episode scene files found in that story.')
    result = render_batch(paths, args.output, progress=lambda value, message: print(f'{value:.0%} {message}', flush=True))
    print(json.dumps(result, indent=2))
    if any(item['status'] != 'verified' for item in result):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
