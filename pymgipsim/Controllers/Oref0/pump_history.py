class PumpHistoryBuilder:

    @staticmethod
    def build_pump_history(insulin_deliveries: list) -> list:
        """Convert insulin deliveries to oref0 pump history (newest-first).

        Must be newest-first: oref0's calc_temp_treatments silently drops
        entries when timestamps go backwards (oldest-first zeroes out IOB).
        """
        result = []
        for delivery in insulin_deliveries:
            if delivery.get("_type") == "Bolus":
                result.append({
                    "_type": "Bolus",
                    "amount": delivery["amount_Uhr"],
                    "timestamp": delivery["timestamp_str"],
                })
                continue
            result.append({
                "_type": "TempBasal",
                "temp": "absolute",
                "rate": delivery["rate_Uhr"],
                "timestamp": delivery["timestamp_str"],
            })
            result.append({
                "_type": "TempBasalDuration",
                "duration (min)": int(delivery["duration_min"]),
                "timestamp": delivery["timestamp_str"],
            })
        result.reverse()
        return result

    @staticmethod
    def build_carb_history(carb_events: list) -> list:
        result = []
        for event in carb_events:
            result.append({
                "_type": "Carb",
                "carbs": event["amount_g"],
                "timestamp": event["timestamp_str"],
            })
        return result
