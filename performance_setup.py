"""High graphics at native 720p, with a steady 60 FPS target."""
import airsim

COMMANDS = (
    'sg.ViewDistanceQuality 2', 'sg.AntiAliasingQuality 3',
    'sg.ShadowQuality 2', 'sg.PostProcessQuality 2', 'sg.TextureQuality 3',
    'sg.EffectsQuality 2', 'sg.FoliageQuality 2', 'r.ScreenPercentage 100',
    'r.MotionBlurQuality 3', 'r.BloomQuality 3', 'r.AmbientOcclusionLevels 2',
    'r.VolumetricFog 1', 'r.VSync 0', 't.MaxFPS 60',
)


def main():
    client = airsim.MultirotorClient(timeout_value=10)
    client.stopRecording()
    for command in COMMANDS:
        if not client.simRunConsoleCommand(command):
            raise RuntimeError(f'Rendering command rejected: {command}')
    print('High graphics applied at native render scale; recording stopped; 60 FPS target.')


if __name__ == '__main__':
    main()
