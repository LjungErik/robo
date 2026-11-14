"""Robo takes one picture with your camera when you ask, and says what he sees."""
from robo_plugin import RoboError, plugin

ASK = ("Robo, a cute desktop robot, just took this picture with the user's camera because "
       'they said: "{said}". Answer them as Robo, warmly and playfully, in one or two '
       'short spoken sentences about what you see. Plain text only.')


@plugin.command('look at me', 'how do i look', 'what am i holding', 'can you see me',
                'take a picture', 'take a photo')
def look(text):
    try:
        picture = plugin.camera.snapshot()
        return plugin.ai.ask(ASK.format(said=text), image=picture)
    except RoboError as e:
        return f"I couldn't look: {e}"
