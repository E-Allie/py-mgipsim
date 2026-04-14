"""Unit conversions between oref0 and py-mgipsim."""


class UnitBridge:

    @staticmethod
    def mmol_to_mgdl(mmol: float) -> float:
        return mmol * 18.0

    @staticmethod
    def mgdl_to_mmol(mgdl: float) -> float:
        return mgdl / 18.0

    @staticmethod
    def Uhr_to_mUmin(uhr: float) -> float:
        return uhr * 1000.0 / 60.0

    @staticmethod
    def mUmin_to_Uhr(mUmin: float) -> float:
        return mUmin * 60.0 / 1000.0

    @staticmethod
    def g_to_mmol(g: float) -> float:
        return (g / 180.156) * 1000.0

    @staticmethod
    def mmol_to_g(mmol: float) -> float:
        return (mmol / 1000.0) * 180.156