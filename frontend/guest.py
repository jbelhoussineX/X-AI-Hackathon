"""Guest data belongs only to the Streamlit session, never a shared account."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.profiles import ProfileStore, _preferences


class GuestStore:
    def __init__(self, state):
        self.state = state
        self.data = state.setdefault('profile_guest_data', {
            'profile': {'display_name': 'Invité', 'email': '', 'topics': [], 'recent_months': 3},
            'answers': {}, 'history': [], 'favorite': []})

    def get_or_create(self, identity):
        return deepcopy(self.data['profile'])

    def update(self, identity, *, display_name, topics, recent_months):
        name, topics, months = _preferences(display_name, topics, recent_months)
        self.data['profile'].update(display_name=name, topics=topics, recent_months=months)
        return self.get_or_create(identity)

    def answers(self, identity):
        return deepcopy(self.data['answers'])

    def save_answers(self, identity, answers):
        self.data['answers'] = deepcopy(answers)

    favorite_id = staticmethod(ProfileStore.favorite_id)

    def items(self, identity, kind):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        self.data['history'] = [item for item in self.data['history'] if item['saved_at'] >= cutoff]
        return deepcopy(list(reversed(self.data[kind])))

    def save_item(self, identity, kind, payload):
        item_id = uuid4().hex if kind == 'history' else self.favorite_id(payload)
        if not any(item['id'] == item_id for item in self.data[kind]):
            self.data[kind].append(dict(id=item_id, saved_at=datetime.now(timezone.utc).isoformat(), data=deepcopy(payload)))
        return item_id

    def remove_item(self, identity, kind, item_id):
        self.data[kind] = [item for item in self.data[kind] if item['id'] != item_id]

    def delete(self, identity):
        self.state.pop('profile_guest_data', None)
