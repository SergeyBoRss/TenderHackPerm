from geopy.distance import geodesic
from geopy.geocoders import Nominatim

from app.core.config import settings
from app.repositories.procurement_analysis import ProcurementAnalysisRepository


MOSCOW_SPB_REGIONS = {"москва", "санкт-петербург"}
REMOTE_REGIONS = {
    "республика саха (якутия)",
    "магаданская область",
    "чукотский автономный округ",
    "камчатский край",
    "ненецкий автономный округ",
}
KALININGRAD_REGIONS = {"калининградская область"}


class RegionWeightService:
    def __init__(self, repository: ProcurementAnalysisRepository):
        self.repository = repository
        self.geolocator = Nominatim(
            user_agent=settings.geopy_user_agent,
            timeout=settings.geopy_timeout_seconds,
        )

    async def get_weight(self, target_region: str, candidate_region: str | None) -> float:
        if not candidate_region:
            return settings.analytics_fallback_multiplier

        normalized_target = self._normalize_region(target_region)
        normalized_candidate = self._normalize_region(candidate_region)
        if normalized_target == normalized_candidate:
            return 1.0

        target_coords = await self._get_or_geocode(target_region)
        candidate_coords = await self._get_or_geocode(candidate_region)
        if not target_coords or not candidate_coords:
            return settings.analytics_fallback_multiplier

        distance_km = geodesic(target_coords, candidate_coords).km
        distance_factor = 1 / (1 + distance_km / settings.analytics_geo_decay_km)
        return distance_factor * self._anomaly_penalty(normalized_target, normalized_candidate)

    async def _get_or_geocode(self, region: str) -> tuple[float, float] | None:
        cached = await self.repository.fetch_region_geo(region)
        if cached:
            return float(cached["latitude"]), float(cached["longitude"])

        location = self.geolocator.geocode(f"{region}, Russia")
        if not location:
            return None

        await self.repository.upsert_region_geo(
            region=region,
            latitude=float(location.latitude),
            longitude=float(location.longitude),
            geocoder_source="nominatim",
        )
        return float(location.latitude), float(location.longitude)

    @staticmethod
    def _normalize_region(region: str) -> str:
        return " ".join(region.strip().lower().replace("ё", "е").split())

    def _anomaly_penalty(self, target_region: str, candidate_region: str) -> float:
        penalties = [1.0, self._single_region_penalty(target_region), self._single_region_penalty(candidate_region)]
        return min(penalties)

    def _single_region_penalty(self, region: str) -> float:
        if region in MOSCOW_SPB_REGIONS:
            return settings.analytics_moscow_spb_penalty
        if region in REMOTE_REGIONS:
            return settings.analytics_remote_penalty
        if region in KALININGRAD_REGIONS:
            return settings.analytics_kaliningrad_penalty
        return 1.0
