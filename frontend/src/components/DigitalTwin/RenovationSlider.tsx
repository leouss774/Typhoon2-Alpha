interface RenovationSliderProps {
  value: boolean;
  onChange: (value: boolean) => void;
}

export default function RenovationSlider({ value, onChange }: RenovationSliderProps) {
  return (
    <div className="slider-control">
      <label>Simulation travaux</label>
      <div className="slider-toggle-group">
        <button
          className={`toggle-btn ${!value ? "active" : ""}`}
          onClick={() => onChange(false)}
        >
          🏚️ Avant
        </button>
        <button
          className={`toggle-btn ${value ? "active" : ""}`}
          onClick={() => onChange(true)}
        >
          🏠 Après travaux
        </button>
      </div>
    </div>
  );
}
