"""Optional, workspace-scoped Studio MCP server. Starts only when explicitly run."""
import argparse
from pathlib import Path
import uuid

from .story_manager import StoryLibrary, atomic_text
from .scene_builder import load_episode, episode_to_dict
from .video_renderer import asset_errors, render_episode


class StudioTools:
    def __init__(self, root, allow_writes=False, allow_render=False):
        self.root = Path(root).resolve()
        self.library = StoryLibrary(self.root)
        self.allow_writes, self.allow_render = allow_writes, allow_render

    def inside(self, relative):
        path = Path(relative)
        if path.is_absolute() or path.drive:
            raise ValueError('Use a path relative to this Studio workspace')
        result = (self.root / path).resolve()
        if not result.is_relative_to(self.root):
            raise ValueError('Path must stay inside the configured workspace')
        return result

    def episode(self, relative):
        path = self.inside(relative)
        if path.name != 'scenes.json' or not path.is_relative_to(self.root / 'stories'):
            raise ValueError('Choose a stories/.../episodes/.../scenes.json file')
        episode = load_episode(path)
        from .settings import settings_for
        settings = settings_for(episode)
        assets = [asset for s in episode.scenes for asset in (s.visual_asset, s.narration_audio, s.foreground_asset) if asset]
        assets += [settings['music_asset'], settings['narration_asset']]
        assets += [e['asset'] for e in settings['sound_effects']]
        for asset in filter(None, assets):
            if not episode.resolve_asset(asset).is_relative_to(self.root):
                raise ValueError('Episode refers to an asset outside the exposed workspace')
        return episode

    def list_stories(self):
        """List this workspace's series and their episode paths."""
        return [{'title': self.library.story_title(p), 'path': p.relative_to(self.root).as_posix(),
                 'episodes': [e.relative_to(self.root).as_posix() for e in self.library.episodes(p)]}
                for p in self.library.stories() if p.resolve().is_relative_to(self.root)]

    def get_episode(self, episode_path: str):
        """Read structured scenes for an episode within this workspace."""
        return episode_to_dict(self.episode(episode_path))

    def validate_episode(self, episode_path: str):
        """Check local assets and narration. This does not run AI generation."""
        errors = asset_errors(self.episode(episode_path))
        return {'valid': not errors, 'errors': errors}

    def save_script_draft(self, episode_path: str, text: str, structured: bool = False):
        """Save a NEW local draft for human review; never replace a script or scenes."""
        if not self.allow_writes:
            raise ValueError('Draft writes are disabled; launch with --allow-drafts to enable')
        episode = self.episode(episode_path)
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > 1024**2:
            raise ValueError('Draft must contain 1 byte to 1 MiB of text')
        if structured:
            from .connections.generation import parse_script
            parse_script(text)
        folder = episode.directory / 'drafts'
        if not folder.resolve().is_relative_to(self.root):
            raise ValueError('Draft folder must stay inside the workspace')
        path = folder / (uuid.uuid4().hex + ('.json' if structured else '.md'))
        atomic_text(path, text)
        return {'draft': path.relative_to(self.root).as_posix(), 'applied': False}

    def render(self, episode_path: str):
        """Render an episode to a NEW uniquely named MP4 and fully verify it."""
        if not self.allow_render:
            raise ValueError('Rendering is disabled; launch with --allow-render to enable')
        episode = self.episode(episode_path)
        output = self.inside('exports') / f'mcp_{uuid.uuid4().hex}.mp4'
        return render_episode(episode.directory / 'scenes.json', output)


def make_server(root, *, allow_drafts=False, allow_render=False):
    try:
        from mcp.server import MCPServer
    except ImportError:
        raise RuntimeError('Install optional MCP support: python -m pip install -r requirements-integrations.txt') from None
    server = MCPServer('Video Novel Studio')
    operations = StudioTools(root, allow_drafts, allow_render)
    for method in (operations.list_stories, operations.get_episode, operations.validate_episode):
        server.tool()(method)
    if allow_drafts:
        server.tool()(operations.save_script_draft)
    if allow_render:
        server.tool()(operations.render)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--allow-drafts', action='store_true')
    parser.add_argument('--allow-render', action='store_true')
    args = parser.parse_args()
    make_server(args.workspace, allow_drafts=args.allow_drafts, allow_render=args.allow_render).run(transport='stdio')


if __name__ == '__main__':
    main()
