"""GTK dialogs that ask you before a task gets anything (an Approver).

Closing a dialog, or pressing Escape, counts as "no".
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from robo.sandbox import Approver  # noqa: E402


def _ask(heading, title, lines, yes_label, on_answer):
    dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.QUESTION,
                               buttons=Gtk.ButtonsType.NONE, text=heading)
    dialog.set_title('Robo')
    dialog.set_keep_above(True)
    dialog.format_secondary_text(f'Task: {title}\n\n' + '\n'.join('• ' + l for l in lines))
    dialog.add_button('No', Gtk.ResponseType.REJECT)
    dialog.add_button(yes_label, Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.REJECT)     # Enter = the safe answer

    answered = []

    def respond(d, response):
        if not answered:
            answered.append(True)
            d.destroy()
            on_answer(response == Gtk.ResponseType.ACCEPT)
    dialog.connect('response', respond)
    dialog.show_all()
    dialog.present()


class GtkApprover(Approver):
    def ask_permissions(self, title, lines, on_answer):
        _ask('Robo would like permission for a task', title, lines, 'Allow', on_answer)

    def review_changes(self, title, lines, on_answer):
        _ask('Robo changed some of your files. Apply the changes?', title,
             lines + ['', 'Nothing has been changed yet. "No" throws the changes away.'],
             'Apply changes', on_answer)
