class SubscriptionLimitError(Exception):
    def __init__(self, feature, current, limit, current_plan, upgrade_message):
        self.feature = feature
        self.current = current
        self.limit = limit
        self.current_plan = current_plan
        self.upgrade_message = upgrade_message
        super().__init__(upgrade_message)

    def to_response_dict(self):
        return {
            "error": "subscription_limit_reached",
            "feature": self.feature,
            "current": self.current,
            "limit": self.limit,
            "current_plan": self.current_plan,
            "message": self.upgrade_message,
            "action_url": "/billing/upgrade",
        }
