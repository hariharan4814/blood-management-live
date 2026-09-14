import React, { useEffect, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";

export interface MapMarkerItem {
  id: string | number;
  type: "user" | "donor" | "hospital" | "blood_bank";
  title: string;
  latitude: number;
  longitude: number;
  distanceKm?: number | null | undefined;
  badge?: string | undefined;
  details?: {
    bloodGroup?: string | undefined;
    isEligible?: boolean | undefined;
    isActive?: boolean | undefined;
    beds?: number | undefined;
    capacity?: number | undefined;
    address?: string | undefined;
    contactNumber?: string | undefined;
    city?: string | undefined;
    rating?: number | null | undefined;
    reviewCount?: number | undefined;
  } | undefined;
  onClick?: (() => void) | undefined;
}

interface LeafletMapProps {
  center?: [number, number] | undefined;
  zoom?: number | undefined;
  markers?: MapMarkerItem[] | undefined;
  selectedPosition?: [number, number] | null | undefined;
  onPositionChange?: ((pos: [number, number]) => void) | undefined;
  isPicker?: boolean | undefined;
  radiusKm?: number | null | undefined;
  height?: string | undefined;
  className?: string | undefined;
  focusedMarkerId?: string | number | null | undefined;
}

const DEFAULT_CENTER: [number, number] = [13.0827, 80.2707]; // Chennai default

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]!);
}

export function LeafletMap({
  center = DEFAULT_CENTER,
  zoom = 13,
  markers = [],
  selectedPosition = null,
  onPositionChange,
  isPicker = false,
  radiusKm = null,
  height = "420px",
  className = "",
  focusedMarkerId = null,
}: LeafletMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markersLayerRef = useRef<any>(null);
  const pickerMarkerRef = useRef<any>(null);
  const circleLayerRef = useRef<any>(null);
  const [isClient, setIsClient] = useState<boolean>(false);
  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  // Initialize Map
  useEffect(() => {
    if (!isClient || !mapContainerRef.current) return;

    let isMounted = true;

    import("leaflet").then((L) => {
      if (!isMounted || !mapContainerRef.current) return;

      if (mapRef.current) {
        mapRef.current.remove();
      }

      const initialCenter = selectedPosition || center || DEFAULT_CENTER;

      const map = L.map(mapContainerRef.current, {
        center: initialCenter,
        zoom: zoom,
        zoomControl: true,
      });

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
        maxZoom: 19,
      }).addTo(map);

      // Create layers
      const markersLayer = L.layerGroup().addTo(map);
      mapRef.current = map;
      markersLayerRef.current = markersLayer;
      setMapReady(true);

      // Click to pick location
      if (isPicker && onPositionChange) {
        map.on("click", (e: any) => {
          const { lat, lng } = e.latlng;
          onPositionChange([Number(lat.toFixed(6)), Number(lng.toFixed(6))]);
        });
      }

      // Responsive size invalidation
      setTimeout(() => {
        if (mapRef.current) {
          mapRef.current.invalidateSize();
        }
      }, 100);
    });

    return () => {
      isMounted = false;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, [isClient]);

  // Handle Location Picker Draggable Marker
  useEffect(() => {
    if (!isClient || !mapRef.current) return;

    import("leaflet").then((L) => {
      if (!mapRef.current) return;

      if (isPicker) {
        if (pickerMarkerRef.current) {
          pickerMarkerRef.current.remove();
          pickerMarkerRef.current = null;
        }

        if (selectedPosition) {
          const pickerIcon = L.divIcon({
            className: "custom-map-pin",
            html: `
              <div class="relative flex items-center justify-center">
                <div class="absolute -top-9 flex flex-col items-center">
                  <div class="flex items-center justify-center size-9 rounded-full bg-indigo-600 text-white shadow-lg border-2 border-white animate-bounce ring-4 ring-indigo-500/20">
                    <svg class="size-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  </div>
                  <div class="w-1.5 h-3 bg-indigo-800 rounded-b"></div>
                </div>
              </div>
            `,
            iconSize: [36, 42],
            iconAnchor: [18, 42],
          });

          const marker = L.marker(selectedPosition, {
            icon: pickerIcon,
            draggable: true,
          }).addTo(mapRef.current);

          marker.on("dragend", (e: any) => {
            const pos = e.target.getLatLng();
            onPositionChange?.([Number(pos.lat.toFixed(6)), Number(pos.lng.toFixed(6))]);
          });

          pickerMarkerRef.current = marker;
          mapRef.current.setView(selectedPosition, Math.max(mapRef.current.getZoom(), 14));
        }
      }
    });
  }, [isClient, mapReady, selectedPosition, isPicker]);

  // Handle Search Radius Circle
  useEffect(() => {
    if (!isClient || !mapRef.current) return;

    import("leaflet").then((L) => {
      if (!mapRef.current) return;

      if (circleLayerRef.current) {
        circleLayerRef.current.remove();
        circleLayerRef.current = null;
      }

      if (typeof radiusKm === "number" && radiusKm > 0 && center) {
        const circle = L.circle(center, {
          radius: radiusKm * 1000,
          color: "#4f46e5",
          fillColor: "#818cf8",
          fillOpacity: 0.12,
          weight: 1.5,
          dashArray: "4, 6",
        }).addTo(mapRef.current);

        circleLayerRef.current = circle;
      }
    });
  }, [isClient, mapReady, radiusKm, center]);

  // Render Markers
  useEffect(() => {
    if (!isClient || !mapRef.current || !markersLayerRef.current) return;

    import("leaflet").then((L) => {
      if (!mapRef.current || !markersLayerRef.current) return;

      const markersLayer = markersLayerRef.current;
      markersLayer.clearLayers();

      const markerInstances: Record<string | number, any> = {};

      markers.forEach((m) => {
        let pinBg = "bg-rose-600";
        let typeBadge = "";
        let iconSvg = "";

        if (m.type === "donor") {
          pinBg = "bg-rose-600";
          typeBadge = `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">Donor</span>`;
          iconSvg = `<svg class="size-4" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/></svg>`;
        } else if (m.type === "hospital") {
          pinBg = "bg-blue-600";
          typeBadge = `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-200">Hospital</span>`;
          iconSvg = `<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 4v16m8-8H4"/></svg>`;
        } else if (m.type === "blood_bank") {
          pinBg = "bg-emerald-600";
          typeBadge = `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">Blood Bank</span>`;
          iconSvg = `<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>`;
        } else {
          pinBg = "bg-indigo-600";
          typeBadge = `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-indigo-100 text-indigo-800 border border-indigo-200">User</span>`;
          iconSvg = `<svg class="size-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/></svg>`;
        }

        const icon = L.divIcon({
          className: "custom-map-pin",
          html: `
            <div class="flex flex-col items-center">
              <div class="flex items-center justify-center size-8 rounded-full ${pinBg} text-white shadow-md border-2 border-white transition-transform hover:scale-110">
                ${iconSvg}
              </div>
              <div class="w-1 h-2 bg-slate-700/80 rounded-b"></div>
            </div>
          `,
          iconSize: [32, 38],
          iconAnchor: [16, 38],
          popupAnchor: [0, -36],
        });

        const distInfo =
          typeof m.distanceKm === "number"
            ? `<span class="font-semibold text-primary ml-1">· ${m.distanceKm} km away</span>`
            : "";

        const statusBadge =
          typeof m.details?.isActive === "boolean"
            ? m.details.isActive
              ? `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">Active</span>`
              : `<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-200 text-slate-700 border border-slate-300">Inactive</span>`
            : "";

        const donorExtraHtml =
          m.type === "donor"
            ? `<div class="flex items-center gap-1.5 mt-1">
                 ${m.details?.bloodGroup ? `<span class="text-[11px] font-extrabold text-rose-600 bg-rose-50 border border-rose-200 px-1 py-0.2 rounded">${escapeHtml(m.details.bloodGroup)}</span>` : ""}
                 ${
                   m.details?.isEligible !== undefined
                     ? m.details.isEligible
                       ? `<span class="text-[10px] font-medium text-emerald-700 bg-emerald-50 px-1 py-0.2 rounded border border-emerald-200">Eligible</span>`
                       : `<span class="text-[10px] font-medium text-amber-700 bg-amber-50 px-1 py-0.2 rounded border border-amber-200">Not eligible</span>`
                     : ""
                 }
               </div>`
            : "";

        const detailsHtml = m.details?.address
          ? `<p class="text-xs text-slate-500 mt-1">${escapeHtml(m.details.address)}</p>`
          : m.details?.city
            ? `<p class="text-xs text-slate-500 mt-1">${escapeHtml(m.details.city)}</p>`
            : "";

        const contactHtml = m.details?.contactNumber
          ? `<p class="text-xs text-slate-600 mt-1 font-mono">📞 ${escapeHtml(m.details.contactNumber)}</p>`
          : "";

        const ratingHtml =
          typeof m.details?.rating === "number"
            ? `<div class="flex items-center gap-1 mt-1 text-xs text-amber-600 font-semibold">
                 <span>★ ${m.details.rating.toFixed(1)}</span>
                 <span class="text-slate-400 font-normal">(${m.details.reviewCount || 0} approved)</span>
               </div>`
            : "";

        const popupContent = `
          <div class="p-1 max-w-[240px]">
            <div class="flex items-center justify-between gap-2 mb-1">
              <div class="flex items-center gap-1">
                ${typeBadge}
                ${statusBadge}
              </div>
              ${distInfo ? `<span class="text-xs text-indigo-700 font-bold bg-indigo-50 px-1.5 py-0.5 rounded">${m.distanceKm} km</span>` : ""}
            </div>
            <h4 class="font-bold text-sm text-slate-900 leading-tight">${escapeHtml(m.title)}</h4>
            ${donorExtraHtml}
            ${ratingHtml}
            ${detailsHtml}
            ${contactHtml}
          </div>
        `;

        const marker = L.marker([m.latitude, m.longitude], { icon })
          .bindPopup(popupContent)
          .addTo(markersLayer);

        if (m.onClick) {
          marker.on("click", m.onClick);
        }

        markerInstances[m.id] = marker;
      });

      // If a marker is focused from props
      if (focusedMarkerId && markerInstances[focusedMarkerId]) {
        const target = markerInstances[focusedMarkerId];
        mapRef.current.setView(target.getLatLng(), Math.max(mapRef.current.getZoom(), 14));
        target.openPopup();
      }
    });
  }, [isClient, mapReady, markers, radiusKm, focusedMarkerId]);

  // Center change
  useEffect(() => {
    if (mapRef.current && center && !isPicker) {
      mapRef.current.setView(center, mapRef.current.getZoom());
    }
  }, [center, mapReady]);

  if (!isClient) {
    return (
      <div
        className={`w-full ${height} rounded-xl border border-border bg-muted/40 animate-pulse flex flex-col items-center justify-center p-6 text-center ${className}`}
      >
        <div className="size-10 rounded-full bg-muted border border-border flex items-center justify-center mb-3">
          <svg className="size-5 text-muted-foreground animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        </div>
        <p className="text-sm font-medium text-foreground">Loading OpenStreetMap...</p>
        <p className="text-xs text-muted-foreground mt-1">Initializing geographical map and markers</p>
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden rounded-xl border border-border shadow-sm ${height} ${className}`}>
      <div ref={mapContainerRef} className="size-full z-0" />
    </div>
  );
}
