interface TimelineSliderProps {
  value: number;
  onChange: (year: number) => void;
}

export default function TimelineSlider({ value, onChange }: TimelineSliderProps) {
  return (
    <div className="slider-control">
      <label>Projection climatique</label>
      <div className="slider-input-group">
        <span className={`slider-year ${value === 2025 ? "active" : ""}`}>2025</span>
        <input
          type="range"
          min={2025}
          max={2050}
          step={25}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="slider"
        />
        <span className={`slider-year ${value === 2050 ? "active" : ""}`}>2050</span>
      </div>
    </div>
  );
}
