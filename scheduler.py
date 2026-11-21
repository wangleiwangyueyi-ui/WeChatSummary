"""Durable local schedule: one merged catch-up, commit only after success."""
from datetime import datetime, timedelta
import json
import uuid
from secure_store import BASE, atomic_bytes

def latest_due(now, schedule):
    from jobs import times
    slots = [now.replace(hour=int(t[:2]), minute=int(t[3:]), second=0, microsecond=0)
             for t in times(schedule)]
    return max(t if t <= now else t-timedelta(days=1) for t in slots)

def next_due(now, schedule):
    from jobs import times
    slots = [now.replace(hour=int(t[:2]), minute=int(t[3:]), second=0, microsecond=0)
             for t in times(schedule)]
    return min(t if t > now else t+timedelta(days=1) for t in slots)

class Scheduler:
    def __init__(self, path=None):
        self.path = path or BASE/'scheduler_state.json'
        self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}

    def save(self):
        atomic_bytes(self.path, json.dumps(self.state, ensure_ascii=False, indent=2).encode('utf-8'))

    def activate(self, now):
        # Explicit resume starts a new schedule; an unfinished run is retained.
        self.state.setdefault('cursor', now.isoformat())
        self.save()

    def prepare(self, now, schedule, rooms):
        if not rooms:
            return None
        pending = self.state.get('pending')
        if pending:
            # Removing a group must also remove it from an unfinished job.
            remaining = [r for r in pending['rooms'] if r in rooms]
            if remaining != pending['rooms']:
                pending['rooms'] = remaining
                self.save()
            if not remaining:
                self.state.pop('pending')
                self.save()
            else:
                return pending if now.timestamp() >= self.state.get('retry_after', 0) else None
        if 'cursor' not in self.state:
            self.activate(now)
            return None
        due = latest_due(now, schedule)
        if due <= datetime.fromisoformat(self.state['cursor']):
            return None
        previous = self.state.get('coverage_end')
        end = now.replace(microsecond=0)
        start = datetime.fromisoformat(previous)+timedelta(seconds=1) if previous else end-timedelta(days=1)
        if start > end:  # local clock moved backwards
            return None
        job = dict(id=uuid.uuid4().hex, due=due.isoformat(), start=start.isoformat(),
                   end=end.isoformat(), rooms=list(rooms))
        self.state['pending'] = job
        self.state['retry_after'] = 0
        self.save()
        return job

    def finish(self, job_id):
        job = self.state.get('pending')
        if job and job['id'] == job_id:
            self.state.update(cursor=job['due'], coverage_end=job['end'], last_success=datetime.now().isoformat())
            self.state.pop('pending')
            self.state.pop('retry_after', None)
            self.save()

    def failed(self, now):
        if self.state.get('pending'):
            self.state['retry_after'] = now.timestamp()+300
            self.save()

    def replace_state(self, state):
        atomic_bytes(self.path, json.dumps(state, ensure_ascii=False, indent=2).encode('utf-8'))
        self.state = state

    def clear_plan(self):
        """Clear pending work and start any future plan with fresh coverage."""
        plan_keys = {'pending', 'retry_after', 'cursor', 'coverage_end'}
        self.replace_state({key: value for key, value in self.state.items() if key not in plan_keys})

    def cancel(self, job_id):
        """Discard this occurrence while leaving the last successful coverage intact."""
        job = self.state.get('pending')
        if not job or job['id'] != job_id:
            return False
        state = {key: value for key, value in self.state.items() if key not in ('pending', 'retry_after')}
        state['cursor'] = job['due']
        self.replace_state(state)
        return True

