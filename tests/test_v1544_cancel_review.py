"""15.4.4: Abbruch, verlassene Arbeit und abgeschottete Code-Pruefungen."""

import contextlib
import importlib
import json
import threading
import time
from types import SimpleNamespace

import pytest

from aquaticy import agent as agents
from aquaticy import review_scan
from aquaticy.agent import Abgebrochen, Agent
from aquaticy.tools import Toolbox


def _call(number, name, **arguments):
    return {'id': f'call{number}', 'type': 'function', 'function': {
        'name': name, 'arguments': json.dumps(arguments)}}


def _thread(fn):
    errors = []
    def run():
        try:
            fn()
        except Abgebrochen:
            pass
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    return thread, errors


def test_c01_an_abandoned_round_cannot_write_into_the_next_turn(settings, monkeypatch):
    agent = Agent(settings)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    def dispatch(box, name, args):
        calls.append(args['text'])
        if args['text'] == 'first':
            entered.set()
            assert release.wait(3)
        return {'saved': True}
    actual = agents.run_calls
    def observe(*args, **kwargs):
        try:
            return actual(*args, **kwargs)
        finally:
            finished.set()
    monkeypatch.setattr(Toolbox, '_call', dispatch)
    monkeypatch.setattr(agents, 'run_calls', observe)
    thread, errors = _thread(lambda: agent._run_round([
        _call(1, 'save_memory', text='first'), _call(2, 'save_memory', text='late')]))
    try:
        assert entered.wait(2)
        agent.cancel()
        thread.join(1)
        assert not thread.is_alive()
        agent._stop = threading.Event()
    finally:
        release.set()
        thread.join(2)
    assert finished.wait(2)
    assert not errors and calls == ['first']
    agent.close()


def test_abandoned_nested_workers_do_not_emit_or_pollute_new_turn_stats(settings, monkeypatch):
    events = []
    agent = Agent(settings, on_event=lambda event, payload: events.append(event))
    entered = threading.Barrier(3)
    release, finished = threading.Event(), threading.Event()
    def dispatch(box, name, args):
        entered.wait(2)
        assert release.wait(3)
        box.stats.searches.append('old-private-query')
        box._emit('late-fetch')
        return {'text': 'old'}
    actual = agents.run_calls
    def observe(*args, **kwargs):
        try:
            return actual(*args, **kwargs)
        finally:
            finished.set()
    monkeypatch.setattr(Toolbox, '_call', dispatch)
    monkeypatch.setattr(agents, 'run_calls', observe)
    thread, errors = _thread(lambda: agent._run_round([
        _call(1, 'fetch_page', url='https://one.example'),
        _call(2, 'fetch_page', url='https://two.example')]))
    try:
        entered.wait(2)
        agent.cancel()
        thread.join(1)
        assert not thread.is_alive()
        agent._stop = threading.Event()
        agent.toolbox.stats.reset()
        events.clear()
    finally:
        release.set()
        thread.join(2)
    assert finished.wait(2)
    assert not errors
    assert 'late-fetch' not in events and not agent.toolbox.stats.searches
    agent.close()


def test_c02_a_cancelled_queued_model_call_never_starts_later(settings, monkeypatch):
    importlib.import_module("litellm")
    agent = Agent(settings)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    @contextlib.contextmanager
    def gate(*args):
        entered.set()
        assert release.wait(3)
        yield
    def model(**kwargs):
        calls.append(kwargs['model'])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='late', tool_calls=None))])
    monkeypatch.setattr(agents, 'paced', gate)
    monkeypatch.setattr(agents.llmcall, 'completion', model)
    def request():
        try:
            agent._completion_with_retry([{'role': 'user', 'content': 'question'}], stream=False)
        finally:
            finished.set()
    thread, errors = _thread(request)
    try:
        assert entered.wait(3), errors
        agent.cancel()
        thread.join(1)
        assert not thread.is_alive()
        agent.settings.model = 'mistral/new-model'
        agent._stop = threading.Event()
    finally:
        release.set()
        thread.join(2)
    assert finished.wait(2)
    time.sleep(0.05)
    assert not errors and calls == []
    agent.close()


def test_c03_abandoned_steps_have_a_resource_limit(settings):
    agent = Agent(settings)
    release = threading.Event()
    lock = threading.Lock()
    active, maximum = [0], [0]
    def slow():
        with lock:
            active[0] += 1
            maximum[0] = max(maximum[0], active[0])
        try:
            release.wait(4)
        finally:
            with lock:
                active[0] -= 1
    try:
        for _ in range(12):
            agent._stop = threading.Event()
            thread, _ = _thread(lambda: agent._abbrechbar(slow))
            time.sleep(0.01)
            agent.cancel()
            thread.join(1)
            assert not thread.is_alive()
        assert maximum[0] <= 4
    finally:
        release.set()
        agent.close()


def test_c04_a_stop_set_just_before_a_step_finishes_is_not_lost(settings):
    agent = Agent(settings)
    def finish():
        agent.cancel()
        return 'old answer'
    with pytest.raises(Abgebrochen):
        agent._abbrechbar(finish)
    agent.close()


def test_c05_a_blocking_final_answer_also_releases_the_caller_on_cancel(settings, monkeypatch):
    agent = Agent(settings)
    entered, release = threading.Event(), threading.Event()
    def model(**kwargs):
        entered.set()
        assert release.wait(3)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='late final answer'))])
    monkeypatch.setattr(agents.llmcall, 'completion', model)
    thread, errors = _thread(lambda: agent._final_answer(stream=False))
    try:
        assert entered.wait(3), errors
        agent.cancel()
        thread.join(0.5)
        assert not thread.is_alive()
    finally:
        release.set()
        thread.join(2)
        agent.close()
    assert not errors


def test_c06_prefetched_news_is_cancellable_too(settings, monkeypatch):
    agent = Agent(settings)
    entered, release = threading.Event(), threading.Event()
    def dispatch(box, name, args):
        entered.set()
        assert release.wait(3)
        return {'results': []}
    monkeypatch.setattr(Toolbox, '_call', dispatch)
    thread, errors = _thread(lambda: agent._prefetch_news('Was sind die neuesten Nachrichten?'))
    try:
        assert entered.wait(2)
        agent.cancel()
        thread.join(0.5)
        assert not thread.is_alive()
    finally:
        release.set()
        thread.join(2)
        agent.close()
    assert not errors


def test_r01_review_vm_has_no_network_or_messenger_volumes(settings):
    settings.vm_user_mode = True
    settings.vm_internet = True
    settings.vm_lan = True
    box = Toolbox(settings)
    box.review_mode = True
    review = box._sandbox()
    assert not review.user_mode and not review.internet and not review.lan
    assert not review.addon_mounts
    box.close()


def test_r02_review_execution_limit_and_timeout_are_enforced(settings):
    box = Toolbox(settings)
    box.review_mode = True
    calls = []
    fake = SimpleNamespace(run=lambda *args, **kwargs: calls.append((args, kwargs)) or
                           SimpleNamespace(as_dict=lambda: {'exit_code': 0}))
    box._review_box = fake
    box._sandbox_box = fake
    for _ in range(5):
        assert not box.vm_run('python3 test.py', timeout=3600).get('error')
    assert box.vm_run('python3 test.py', timeout=3600).get('error')
    assert len(calls) == 5 and all(c[1]['timeout'] <= 20 for c in calls)


@pytest.mark.parametrize('number', ['NaN', 'Infinity', '-Infinity'])
def test_r03_json_syntax_review_rejects_non_json_constants(number):
    assert review_scan.syntax_problems('```json\n{"value": ' + number + '}\n```')


def test_successful_final_answer_remains_in_the_conversation(settings, monkeypatch):
    agent = Agent(settings)
    monkeypatch.setattr(agents.llmcall, 'completion', lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='Zusammenfassung'))]))
    try:
        assert agent._final_answer(stream=False) == 'Zusammenfassung'
        assert agent.messages[-1] == {'role': 'assistant', 'content': 'Zusammenfassung'}
    finally:
        agent.close()
