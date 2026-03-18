/**
 * GoogleMapsEmbed — renders an iframe with the Google Maps Embed API.
 * Shows a directions/place view for the charted shipping route.
 *
 * NOTE: The Maps Embed API only supports land transport modes (driving,
 * walking, transit, bicycling) — NOT maritime routes. For ocean routes
 * we use "place" mode centred between origin and destination.
 * The actual route line is rendered on the Deck.gl "Whale Layers" tab.
 */

interface GoogleMapsEmbedProps {
    /** Pre-built embed URL from the backend (preferred), or build from origin/dest. */
    embedUrl?: string;
    /** Origin port name — used if embedUrl is not provided. */
    origin?: string;
    /** Destination port name — used if embedUrl is not provided. */
    destination?: string;
    /** API key for Maps Embed API. */
    apiKey?: string;
}

const FALLBACK_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "";

export function GoogleMapsEmbed({
    embedUrl,
    origin,
    destination,
    apiKey,
}: GoogleMapsEmbedProps) {
    const key = apiKey || FALLBACK_API_KEY;

    // Prefer backend-provided URL (has real waypoints from google_maps_router)
    let url = embedUrl || "";

    if (!url && key && origin && destination) {
        // Build a directions embed as reference view
        const params = new URLSearchParams({
            key,
            origin,
            destination,
            mode: "driving", // No maritime mode — best-effort land reference
        });
        url = `https://www.google.com/maps/embed/v1/directions?${params.toString()}`;
    }

    if (!url) {
        return (
            <div className="flex h-full w-full items-center justify-center text-muted-foreground">
                <div className="text-center">
                    <p className="text-lg font-medium">Google Maps</p>
                    <p className="mt-1 text-sm">
                        {!key
                            ? "Maps API key not configured. Enable the Maps Embed API on your GCP project."
                            : "Submit a route query to see it on Google Maps."}
                    </p>
                </div>
            </div>
        );
    }

    return (
        <iframe
            src={url}
            width="100%"
            height="100%"
            style={{ border: 0, borderRadius: "8px" }}
            allowFullScreen
            loading="lazy"
            referrerPolicy="no-referrer-when-downgrade"
            title="Google Maps Route"
        />
    );
}
