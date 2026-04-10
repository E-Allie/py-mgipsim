"""Unit conversion bridge for oref0 <-> py-mgipsim integration.

All conversions are static methods. No inline arithmetic anywhere else in the
oref0 controller - all unit math goes through this class.
"""


class UnitBridge:
    # Glucose: mmol/L <-> mg/dL
    # Use factor 18 (matching py-mgipsim's UnitConversion.glucose)

    @staticmethod
    def mmol_to_mgdl(mmol: float) -> float:
        """Convert glucose from mmol/L to mg/dL. Factor: 18."""
        return mmol * 18.0

    @staticmethod
    def mgdl_to_mmol(mgdl: float) -> float:
        """Convert glucose from mg/dL to mmol/L. Factor: 1/18."""
        return mgdl / 18.0

    # Insulin: U/hr <-> mU/min
    @staticmethod
    def Uhr_to_mUmin(uhr: float) -> float:
        """Convert insulin rate from U/hr to mU/min."""
        return uhr * 1000.0 / 60.0

    @staticmethod
    def mUmin_to_Uhr(mUmin: float) -> float:
        """Convert insulin rate from mU/min to U/hr."""
        return mUmin * 60.0 / 1000.0

    # Carbs: g <-> mmol (glucose molecular weight 180.156 g/mol)
    @staticmethod
    def g_to_mmol(g: float) -> float:
        """Convert glucose mass from grams to mmol."""
        return (g / 180.156) * 1000.0

    @staticmethod
    def mmol_to_g(mmol: float) -> float:
        """Convert glucose mass from mmol to grams."""
        return (mmol / 1000.0) * 180.156