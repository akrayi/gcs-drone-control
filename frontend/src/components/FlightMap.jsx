import React from "react";
export default function FlightMap({ state, target, setTarget }) {
  return (
    <section className="panel map-panel">
      <div className="panel-heading">
        <h2>Flight area</h2>
        <span className="muted">200 × 200 m · click to set target</span>
      </div>
      <svg
        className="map"
        viewBox="0 0 600 450"
        role="img"
        aria-label="Interactive drone map; target can also be set with coordinate fields"
        onClick={(e) => {
          const p = e.currentTarget.createSVGPoint();
          p.x = e.clientX;
          p.y = e.clientY;
          const loc = p.matrixTransform(
            e.currentTarget.getScreenCTM().inverse(),
          );
          setTarget({
            x: Math.max(-100, Math.min(100, Math.round((loc.x - 300) / 2))),
            y: Math.max(-100, Math.min(100, Math.round((225 - loc.y) / 2))),
          });
        }}
      >
        <defs>
          <pattern
            id="grid"
            width="40"
            height="40"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 40 0 L 0 0 0 40"
              fill="none"
              stroke="#1e3041"
              strokeWidth="1"
            />
          </pattern>
          <radialGradient id="glow">
            <stop stopColor="#1b746c" stopOpacity=".2" />
            <stop offset="1" stopColor="#0b1723" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width="600" height="450" fill="#0b1723" />
        <rect width="600" height="450" fill="url(#grid)" />
        <circle cx="300" cy="225" r="210" fill="url(#glow)" />
        <rect
          x="100"
          y="25"
          width="400"
          height="400"
          rx="8"
          fill="none"
          stroke="#325165"
          strokeDasharray="6 6"
        />
        <path
          d="M300 25V425M100 225H500"
          stroke="#274252"
          strokeDasharray="3 5"
        />
        <circle cx="300" cy="225" r="18" fill="#173a39" stroke="#3e8d7e" />
        <text x="300" y="230" textAnchor="middle" fill="#8fe5ce" fontSize="14">
          H
        </text>
        <text x="300" y="263" textAnchor="middle" fill="#71909f" fontSize="10">
          HOME · 0, 0
        </text>
        <g transform={`translate(${300 + target.x * 2},${225 - target.y * 2})`}>
          <circle r="8" fill="none" stroke="#eac37b" />
          <path d="M-12 0H12M0 -12V12" stroke="#eac37b" />
        </g>
        {state && (
          <g
            className="drone"
            transform={`translate(${300 + state.x * 2},${225 - state.y * 2})`}
          >
            <circle r="29" fill="#72eadb" opacity=".08" />
            <path
              d="M-13 -13L13 13M-13 13L13 -13"
              stroke="#b4fff1"
              strokeWidth="4"
            />
            {[
              [-14, -14],
              [14, -14],
              [-14, 14],
              [14, 14],
            ].map(([x, y]) => (
              <circle
                key={`${x},${y}`}
                cx={x}
                cy={y}
                r="8"
                fill="#0e2d33"
                stroke="#6ee7cf"
                strokeWidth="2"
              />
            ))}
            <rect x="-6" y="-8" width="12" height="16" rx="4" fill="#b4fff1" />
          </g>
        )}
        <text x="24" y="30" fill="#75909f" fontSize="11">
          N ↑
        </text>
        <text x="24" y="429" fill="#75909f" fontSize="11">
          SIMULATED TELEMETRY · METERS
        </text>
      </svg>
      <div className="map-footer">
        <span>
          <i className="dot" /> Drone 01
        </span>
        <span className="muted">
          Transitions are immediate; map animation is illustrative.
        </span>
      </div>
    </section>
  );
}
