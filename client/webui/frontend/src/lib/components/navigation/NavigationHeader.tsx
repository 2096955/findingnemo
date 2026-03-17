import React, { useState, useEffect } from "react";
import { useConfigContext } from "@/lib/hooks/useConfigContext";

const LOGO_URL_STORAGE_KEY = "webui_logo_url";

const HEADER_ICON = (
    <div className="flex h-12 w-12 items-center justify-center overflow-hidden rounded-full">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">
            {/* Whale tail icon */}
            <path
                className="fill-[var(--color-brand-wMain)]"
                d="M50 15c-8 0-15 4-20 10-6 7-10 17-10 28 0 5 1 10 3 14 2 5 6 8 10 10 3 1 6 2 9 2h16c3 0 6-1 9-2 4-2 8-5 10-10 2-4 3-9 3-14 0-11-4-21-10-28-5-6-12-10-20-10z"
                opacity="0.15"
            />
            <path
                className="fill-[var(--color-brand-wMain)]"
                d="M30 25c-4 6-7 14-7 23 0 12 5 20 13 24h28c8-4 13-12 13-24 0-9-3-17-7-23-5-7-11-10-20-10s-15 3-20 10z"
                opacity="0.3"
            />
            {/* Whale body */}
            <ellipse cx="50" cy="52" rx="28" ry="20" className="fill-[var(--color-brand-wMain)]" />
            {/* Whale tail flukes */}
            <path
                className="fill-[var(--color-brand-wMain)]"
                d="M15 30c-5-8-12-14-12-14s4 12 6 18c2 5 4 8 8 10l3-6c-2-2-4-5-5-8z"
            />
            <path
                className="fill-[var(--color-brand-wMain)]"
                d="M15 30c-1-9-5-18-5-18s-2 13-1 19c1 5 3 9 6 12l4-5c-2-2-3-5-4-8z"
            />
            {/* Whale spout */}
            <path
                d="M55 28c0-3 1-7 3-12M52 30c-1-4-1-9 0-15M58 29c1-3 3-6 6-10"
                stroke="var(--color-brand-wMain)"
                strokeWidth="2"
                strokeLinecap="round"
                fill="none"
                opacity="0.6"
            />
            {/* Eye */}
            <circle cx="65" cy="48" r="3" fill="white" />
            <circle cx="66" cy="48" r="1.5" className="fill-[var(--color-brand-w100)]" />
            {/* Smile */}
            <path
                d="M62 56c3 2 7 3 10 2"
                stroke="white"
                strokeWidth="1.5"
                strokeLinecap="round"
                fill="none"
                opacity="0.8"
            />
            {/* Flipper */}
            <ellipse cx="48" cy="60" rx="8" ry="4" className="fill-[var(--color-brand-w100)]" opacity="0.3" transform="rotate(-20 48 60)" />
        </svg>
    </div>
);

interface NavigationHeaderProps {
    onClick?: () => void;
}

export const NavigationHeader: React.FC<NavigationHeaderProps> = ({ onClick }) => {
    const config = useConfigContext();
    const [imageError, setImageError] = useState(false);
    const [logoUrl, setLogoUrl] = useState<string>("");
    const botName = config.configBotName;

    // Update document title when botName is available
    useEffect(() => {
        if (botName) {
            document.title = botName;
        }
    }, [botName]);

    // Load cached logo URL immediately on mount for instant display
    useEffect(() => {
        try {
            const cachedLogoUrl = localStorage.getItem(LOGO_URL_STORAGE_KEY);
            if (cachedLogoUrl) {
                setLogoUrl(cachedLogoUrl);
            }
        } catch (err) {
            console.warn("Failed to read cached logo URL from localStorage:", err);
        }
    }, []);

    // Update logo URL when config changes (after API call completes)
    useEffect(() => {
        if (config.configLogoUrl !== undefined) {
            setLogoUrl(config.configLogoUrl);
            try {
                localStorage.setItem(LOGO_URL_STORAGE_KEY, config.configLogoUrl);
            } catch (error) {
                console.error("Failed to save logo URL to localStorage:", error);
            }
            // Reset image error state when logo URL changes
            setImageError(false);
        }
    }, [config.configLogoUrl]);

    const shouldShowCustomLogo = logoUrl && !imageError;

    return (
        <div className="flex h-[80px] min-h-[80px] cursor-pointer items-center justify-center border-b" onClick={onClick} title={botName || undefined}>
            {shouldShowCustomLogo ? (
                <div className="flex h-16 w-16 items-center justify-center overflow-hidden">
                    <img src={logoUrl} alt={botName || "Logo"} className="h-full w-full object-contain" onError={() => setImageError(true)} />
                </div>
            ) : (
                HEADER_ICON
            )}
        </div>
    );
};
