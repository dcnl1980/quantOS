class LiveTradingDisabled(RuntimeError): pass

class LiveBroker:
    def __init__(self,enabled,acknowledgement):
        if not enabled or acknowledgement!="I_UNDERSTAND_REAL_MONEY_IS_AT_RISK":
            raise LiveTradingDisabled("Explicit live-trading configuration acknowledgement required.")
        raise NotImplementedError("Implement venue-specific authenticated adapters, reconciliation and testnet validation first.")
