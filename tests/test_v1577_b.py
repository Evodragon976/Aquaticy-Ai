"""15.7.7: Wartende Messenger-Meldungen bleiben an Konto und Einwilligung gebunden."""

import threading
from types import SimpleNamespace

import pytest

from aquaticy import messenger_native as native
from aquaticy import web


@pytest.fixture
def hub(tmp_path):
    clock = [100_000.0]
    state = {'wanted': True, 'paused': False, 'recipients': []}

    class Transport:
        def __init__(self, *args, **kwargs):
            self.state = native.CONNECTED
            self.running = True
            self.who = '+491700000001'
            self.store = SimpleNamespace(who=lambda name: self.who)
            self.sent = []
            self.fail = False
            self.hook = None

        def has_session(self):
            return bool(self.who)

        def own_chat(self):
            return 'self' if self.who else ''

        def status(self):
            return SimpleNamespace(state=self.state)

        def send(self, target, text):
            if self.fail:
                raise OSError('connection interrupted')
            self.sent.append((target, text))
            if self.hook:
                self.hook(target, text)

        def start(self):
            self.running = True

        def stop(self):
            self.running = False

        def unlink(self):
            self.stop()
            self.who = ''

        def available(self):
            return True, ''

    instance = native.NativeHub(tmp_path, lambda *args: None,
                               lambda name: state['wanted'],
                               factories={name: Transport for name in native.MESSENGERS},
                               clock=lambda: clock[0], paused=lambda: state['paused'])
    instance.recipients = lambda name: state['recipients']
    yield instance, state, clock
    instance.stop()


def test_f015_failed_flushes_keep_pending_notifications_for_the_next_attempt(hub):
    instance, _, _ = hub
    transport = instance.transport('signal')
    transport.state = native.STARTING
    assert instance.message_owner('signal', 'Private reminder') == 'wartet'
    transport.state, transport.fail = native.CONNECTED, True
    instance._flush('signal')
    transport.fail = False
    instance._flush('signal')
    assert transport.sent == [('self', 'Private reminder')]


def test_f016_a_transient_connected_send_failure_does_not_discard_coworker_reports(hub):
    instance, _, _ = hub
    transport = instance.transport('signal')
    transport.fail = True
    instance.notify_owner('Coworker result')
    transport.fail = False
    instance._flush('signal')
    assert transport.sent == [('self', 'Coworker result')]


@pytest.mark.parametrize('unlink', [True, False])
def test_f017_pending_private_messages_never_move_to_a_different_linked_owner(hub, unlink):
    instance, _, _ = hub
    transport = instance.transport('signal')
    transport.state = native.STARTING
    instance.message_owner('signal', 'First account private message')
    if unlink:
        instance.unlink('signal')
    transport.who = '+491700000002'
    transport.state = native.CONNECTED
    instance._flush('signal')
    assert transport.sent == []


def test_f018_late_callbacks_cannot_send_after_the_hub_was_stopped(hub):
    instance, _, _ = hub
    transport = instance.transport('signal')
    transport.state = native.STARTING
    instance.message_owner('signal', 'Private pending message')
    web._stop_native(instance)
    transport.state = native.CONNECTED
    instance._flush('signal')
    assert transport.sent == []


def test_stopped_hubs_also_discard_late_incoming_callbacks(hub):
    instance, _, _ = hub
    answered = threading.Event()
    instance._responder = lambda *args: answered.set()
    web._stop_native(instance)
    instance._enqueue('signal', SimpleNamespace())
    assert not answered.wait(0.15)


def test_f019_a_removed_recipient_cannot_receive_a_burst_already_in_progress(hub):
    instance, state, _ = hub
    state['recipients'] = ['+4915112345678']
    transport = instance.transport('signal')
    transport.hook = lambda target, text: state['recipients'].clear()
    instance.notify_owner('Private report')
    assert transport.sent == [('self', 'Private report')]


def test_f020_pausing_during_delivery_stops_further_messenger_channels(hub):
    instance, state, _ = hub
    first = instance.transport('whatsapp')
    first.hook = lambda *args: state.update(paused=True)
    instance.alert_owner('Security report')
    assert first.sent == [('self', 'Security report')]
    assert instance.transport('signal').sent == []


def test_f021_active_queues_purge_messages_after_the_documented_retention_time(hub):
    instance, _, clock = hub
    transport = instance.transport('signal')
    transport.state = native.STARTING
    instance.message_owner('signal', 'Expired private content')
    clock[0] += native.NOTIFY_KEEP_SECONDS + 1
    instance.message_owner('signal', 'Current private content')
    assert 'Expired private content' not in str(instance._pending)
    assert 'Current private content' in str(instance._pending)


def test_f022_one_broken_messenger_cannot_block_alerts_on_a_healthy_channel(hub):
    instance, _, _ = hub

    def broken():
        raise OSError('unreadable session metadata')

    instance.transport('whatsapp').has_session = broken
    assert instance.alert_owner('Important') == ['signal']
    assert instance.transport('signal').sent == [('self', 'Important')]


def test_a_temporarily_stopped_hub_preserves_notices_for_its_next_start(hub):
    instance, _, _ = hub
    transport = instance.transport("signal")
    transport.state = native.STARTING
    instance.message_owner("signal", "Private reminder")
    instance.stop()
    transport.state = native.CONNECTED
    instance._flush("signal")
    assert transport.sent == [("self", "Private reminder")]
