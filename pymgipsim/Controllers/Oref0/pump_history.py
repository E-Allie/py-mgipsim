"""Builds oref0-compatible pump history JSON from StateTracker insulin deliveries."""


class PumpHistoryBuilder:

    @staticmethod
    def build_pump_history(insulin_deliveries: list) -> list:
        """Convert insulin delivery records to oref0 pump history format.

        Args:
            insulin_deliveries: list of dicts from StateTracker (chronological order), each with:
                - timestamp_str: ISO 8601 string
                - rate_Uhr: float (U/hr)
                - duration_min: float (minutes)

        Returns:
            list of oref0 pump history entries in newest-first order. oref0's
            calc_temp_treatments skips any record where timestamp > last_record_ms
            (it expects pump history sorted newest-first, matching Medtronic pump
            dumps). Feeding oldest-first causes silent drop of every entry after
            the first, zeroing out IOB.
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
        """Convert carb event records to oref0 carb history format.

        Args:
            carb_events: list of dicts from StateTracker, each with:
                - timestamp_str: ISO 8601 string
                - amount_g: float (grams)

        Returns:
            list of oref0 carb history entries
        """
        result = []
        for event in carb_events:
            result.append({
                "_type": "Carb",
                "carbs": event["amount_g"],
                "timestamp": event["timestamp_str"],
            })
        return result
