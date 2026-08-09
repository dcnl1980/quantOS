"""Live trading gate. Production capital requires explicit acknowledgement after testnet promotion."""


class LiveTradingDisabled(RuntimeError):
    pass


class LiveBroker:
    """
    Hard gate for real-money routing.

    H2 provides authenticated *testnet* brokers via ExecutionGateway.
    Live capital still requires ENABLE_LIVE_TRADING + acknowledgement and is not
    auto-enabled by EXECUTION_MODE=live alone.
    """

    ACK = "I_UNDERSTAND_REAL_MONEY_IS_AT_RISK"

    def __init__(self, enabled: bool, acknowledgement: str, testnet_validated: bool = False):
        if not enabled or acknowledgement != self.ACK:
            raise LiveTradingDisabled(
                "Explicit live-trading configuration acknowledgement required."
            )
        if not testnet_validated:
            raise LiveTradingDisabled(
                "Promote through EXECUTION_MODE=testnet and reconciliation gates before live."
            )
        raise NotImplementedError(
            "Implement venue-specific authenticated live adapters with signing, "
            "user-data streams, and production reconciliation."
        )
