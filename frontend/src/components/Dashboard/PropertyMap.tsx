import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";

interface PropertyMapProps {
  lat: number;
  lng: number;
  adresse: string;
}

export default function PropertyMap({ lat, lng, adresse }: PropertyMapProps) {
  return (
    <div className="property-map-card">
      <h3>Localisation du bien</h3>
      <div className="property-map-container">
        <MapContainer
          center={[lat, lng]}
          zoom={14}
          scrollWheelZoom={false}
          style={{ height: "100%", width: "100%", borderRadius: "8px" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <Marker position={[lat, lng]}>
            <Popup>{adresse}</Popup>
          </Marker>
        </MapContainer>
      </div>
    </div>
  );
}
