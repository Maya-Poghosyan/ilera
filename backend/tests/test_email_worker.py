import copy
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
import pytest
from app.email_ingestion import worker as w
from app.email_ingestion.extraction import Extraction
from app.email_ingestion.models import EmailMessage, EmailScanJob, MailboxConnection
from test_email_extraction import event


@pytest.fixture
def state(monkeypatch):
    s = NS(events={}, results={}, fetches=0, extractions=0, locked=True, fail_ledger=False,
        fail_commit=False, on_extract=None, active=True)
    s.mailbox = MailboxConnection(id='c', user_id='u', case_id='case', provider='microsoft',
        provider_account_id='account', credential_id='credential', status='connected',
        consented_at=datetime.now(timezone.utc))
    class Conn:
        def execute(self, sql, params):
            self.row = None
            if 'pg_try_advisory' in sql:
                self.row = (s.locked,)
            elif 'SELECT 1 FROM email_scan_results' in sql:
                self.row = (1,) if params[0] in s.results else None
            elif 'SELECT e.doc' in sql:
                assert "c.owner_user_id = e.doc->>'user_id'" in sql
                self.row = (s.mailbox.model_dump(mode='json'),) if s.active else None
            elif 'INSERT INTO suggested_events' in sql:
                s.events[params[0]] = json.loads(params[1])
            elif 'INSERT INTO email_scan_results' in sql:
                if s.fail_ledger:
                    raise RuntimeError('PHI-SENTINEL failed write')
                s.results[params[0]] = json.loads(params[2])
            return self
        def fetchone(self):
            return self.row
    @contextmanager
    def connection():
        before = copy.deepcopy((s.events,s.results))
        try:
            yield Conn()
            if s.fail_commit:
                raise RuntimeError('commit failed')
        except BaseException:
            s.events,s.results = before
            raise
    class Provider:
        async def fetch_message(self, token, message_id):
            s.fetches += 1
            return EmailMessage(message_id=message_id, received_at=datetime.now(timezone.utc),
                sender='SENDER-SECRET', subject='RAW-SUBJECT', body_text='RAW-BODY')
    class Extractor:
        def extract(self, message):
            s.extractions += 1
            if s.on_extract:
                s.on_extract()
            return s.extraction
    s.extraction = Extraction(events=[event(), event(kind='Task')])
    s.extractor = Extractor()
    s.job = EmailScanJob(provider='microsoft', connection_id='c', message_id='m')
    monkeypatch.setattr(w.db,'connection',connection)
    monkeypatch.setattr(w.db,'available',lambda: True)
    monkeypatch.setattr(w,'get_settings',lambda: NS(email_scanning_enabled=True,email_scan_max_deliveries=5))
    monkeypatch.setattr(w.connections,'access_token',lambda **kw:'token')
    monkeypatch.setattr(w.connections,'_provider',Provider)
    monkeypatch.setattr(w.connections,'_lock',lambda *args:None)
    return s


def test_replay_without_refetch(state):
    assert w.process_job(state.job,state.extractor) == 'suggested'
    assert w.process_job(state.job,state.extractor) == 'duplicate'
    assert state.fetches == state.extractions == 1
    assert len(state.events)==2 and len(state.results)==1
    saved=str(state.events)+str(state.results)
    assert all(x not in saved for x in ['RAW-BODY','RAW-SUBJECT','SENDER-SECRET'])
    assert all(e['user_id']=='u' and e['status']=='pending' for e in state.events.values())


@pytest.mark.parametrize('failure',['fail_ledger','fail_commit'])
def test_rollback_and_retry(state,failure):
    setattr(state,failure,True)
    with pytest.raises(RuntimeError):
        w.process_job(state.job,state.extractor)
    assert not state.events and not state.results
    setattr(state,failure,False)
    assert w.process_job(state.job,state.extractor)=='suggested'
    assert len(state.events)==2


@pytest.mark.parametrize('change',['disconnect','owner','reconnect'])
def test_connection_change_prevents_commit(state,change):
    def mutate():
        if change=='disconnect': state.mailbox.status='disconnected'
        elif change=='owner': state.active=False
        else: state.mailbox.consented_at+=timedelta(seconds=1)
    state.on_extract=mutate
    assert w.process_job(state.job,state.extractor)=='inactive'
    assert not state.events and not state.results


def test_inactive_skips_fetch(state):
    state.mailbox.status='disconnected'
    assert w.process_job(state.job,state.extractor)=='inactive'
    assert state.fetches==0


def test_concurrent_duplicate_skips_fetch(state):
    state.locked=False
    with pytest.raises(w.RetryScan): w.process_job(state.job,state.extractor)
    assert state.fetches==0


def test_no_event_is_durable(state):
    state.extraction=Extraction(events=[])
    assert w.process_job(state.job,state.extractor)=='no_event'
    assert w.process_job(state.job,state.extractor)=='duplicate'
    assert not state.events and len(state.results)==1


def test_ambiguous_event_has_no_day(state):
    state.extraction=Extraction(events=[event(date=None,date_status='ambiguous',time=None,timezone=None)])
    w.process_job(state.job,state.extractor)
    saved=next(iter(state.events.values()))
    assert saved['date'] is None and saved['day']==0


class Receiver:
    def __init__(self): self.actions=[]
    def complete_message(self,msg): self.actions.append('complete')
    def abandon_message(self,msg): self.actions.append('abandon')
    def dead_letter_message(self,msg,**kw):
        assert 'PHI-SENTINEL' not in str(kw)
        self.actions.append('deadletter')


def test_ack_after_commit(state):
    r=Receiver()
    msg=NS(body=[state.job.model_dump_json().encode()],delivery_count=1)
    state.fail_commit=True
    assert w.settle_message(r,msg,state.extractor)=='retry'
    assert r.actions==['abandon']
    state.fail_commit=False
    assert w.settle_message(r,msg,state.extractor)=='suggested'
    assert r.actions==['abandon','complete']


def test_bounded_retry_dlq(state):
    state.fail_ledger=True
    r=Receiver()
    msg=NS(body=[state.job.model_dump_json().encode()],delivery_count=5)
    assert w.settle_message(r,msg,state.extractor)=='dead_lettered'
    assert r.actions==['deadletter']


def test_unknown_payload_not_copied_to_dlq(state):
    r=Receiver()
    msg=NS(body=[b'{"raw_email":"PHI-SENTINEL"}'],delivery_count=1)
    assert w.settle_message(r,msg,state.extractor)=='invalid_job_discarded'
    assert r.actions==['complete'] and state.fetches==0


def test_disconnect_during_fetch_skips_model(state, monkeypatch):
    original = w.connections._provider()
    class Provider:
        async def fetch_message(self, token, message_id):
            message = await original.fetch_message(token, message_id)
            state.mailbox.status = 'disconnected'
            return message
    monkeypatch.setattr(w.connections, '_provider', Provider)
    assert w.process_job(state.job, state.extractor) == 'inactive'
    assert state.extractions == 0 and not state.results


def test_graph_rejection_persists_reconnect_state(state, monkeypatch):
    saved = []
    class Provider:
        async def fetch_message(self, *args):
            raise w.ReauthorizationRequired('fixed')
    monkeypatch.setattr(w.connections, '_provider', Provider)
    monkeypatch.setattr(w.connections, '_write_connection', lambda conn, mailbox: saved.append(mailbox))
    assert w.process_job(state.job, state.extractor) == 'inactive'
    assert saved[0].status == 'reauthorization_required' and saved[0].reconciliation_required
    assert state.extractions == 0
