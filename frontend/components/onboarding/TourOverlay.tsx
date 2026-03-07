'use client'

import { useLayoutEffect, useState } from 'react'
import { STEPS } from './tourState'

interface SpotlightRect {
  top: number
  left: number
  width: number
  height: number
  radius: number
}

interface CardPos {
  top: number
  left: number
}

export function TourOverlay({
  stepIndex,
  onNext,
  onPrev,
  onSkip,
}: {
  stepIndex: number
  onNext: () => void
  onPrev: () => void
  onSkip: () => void
}) {
  const step = STEPS[stepIndex]
  const total = STEPS.length
  const progress = ((stepIndex + 1) / total) * 100

  const [spotlight, setSpotlight] = useState<SpotlightRect | null>(null)
  const [cardPos, setCardPos] = useState<CardPos>({ top: 0, left: 0 })

  useLayoutEffect(() => {
    const padding = step.padding ?? 6
    const radius = step.radius ?? 8

    function measure(): boolean {
      const el = document.querySelector(step.selector)
      if (!el) return false
      const r = el.getBoundingClientRect()
      const sp: SpotlightRect = {
        top: r.top - padding,
        left: r.left - padding,
        width: r.width + padding * 2,
        height: r.height + padding * 2,
        radius,
      }
      setSpotlight(sp)

      const cardW = 288
      const cardH = 200
      const vw = window.innerWidth
      const vh = window.innerHeight
      const side = step.side ?? 'bottom'
      const gap = 12

      let top = 0
      let left = 0

      if (side === 'bottom') {
        top = sp.top + sp.height + gap
        left = sp.left + sp.width / 2 - cardW / 2
      } else if (side === 'top') {
        top = sp.top - cardH - gap
        left = sp.left + sp.width / 2 - cardW / 2
      } else if (side === 'right') {
        top = sp.top + sp.height / 2 - cardH / 2
        left = sp.left + sp.width + gap
      } else {
        top = sp.top + sp.height / 2 - cardH / 2
        left = sp.left - cardW - gap
      }

      left = Math.max(12, Math.min(left, vw - cardW - 12))
      top = Math.max(12, Math.min(top, vh - cardH - 12))

      setCardPos({ top, left })
      return true
    }

    let retries = 0
    const tryMeasure = () => {
      if (measure()) return
      if (retries < 20) {
        retries++
        setTimeout(tryMeasure, 150)
      }
    }
    tryMeasure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [step])

  const vw = window.innerWidth
  const vh = window.innerHeight

  const { top = 0, left = 0, width = 0, height = 0, radius = 8 } = spotlight ?? {}

  const clipPath = spotlight
    ? `M0,0 H${vw} V${vh} H0 Z M${left},${top + radius} Q${left},${top} ${left + radius},${top} H${left + width - radius} Q${left + width},${top} ${left + width},${top + radius} V${top + height - radius} Q${left + width},${top + height} ${left + width - radius},${top + height} H${left + radius} Q${left},${top + height} ${left},${top + height - radius} Z`
    : `M0,0 H${vw} V${vh} H0 Z`

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        pointerEvents: 'none',
        visibility: spotlight ? 'visible' : 'hidden',
      }}
    >
      {/* Dark overlay with cutout */}
      <svg
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'auto',
        }}
        onClick={onSkip}
      >
        <path d={clipPath} fill="rgba(0,0,0,0.72)" fillRule="evenodd" />
      </svg>

      {/* Spotlight border glow */}
      <div
        style={{
          position: 'absolute',
          top,
          left,
          width,
          height,
          borderRadius: radius,
          boxShadow: '0 0 0 2px #b9eb10, 0 0 20px 4px rgba(185,235,16,0.3)',
          pointerEvents: 'none',
        }}
      />

      {/* Card */}
      <div
        style={{
          position: 'absolute',
          top: cardPos.top,
          left: cardPos.left,
          width: 288,
          background: '#1e1e1e',
          border: '1.5px solid rgba(185,235,16,0.27)',
          borderRadius: 16,
          padding: 20,
          boxShadow: '0 8px 40px rgba(0,0,0,0.5)',
          pointerEvents: 'auto',
        }}
      >
        {/* Step counter + skip */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 12,
          }}
        >
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: '0.15em',
              textTransform: 'uppercase',
              color: '#b9eb10',
            }}
          >
            Step {stepIndex + 1} / {total}
          </span>
          <button
            type="button"
            onClick={onSkip}
            style={{
              fontSize: 11,
              color: 'rgba(255,255,255,0.35)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 0,
            }}
          >
            Skip
          </button>
        </div>

        {/* Progress bar */}
        <div
          style={{
            height: 2,
            background: 'rgba(255,255,255,0.1)',
            borderRadius: 2,
            marginBottom: 16,
          }}
        >
          <div
            style={{
              height: 2,
              width: `${progress}%`,
              background: '#b9eb10',
              borderRadius: 2,
              transition: 'width 0.3s',
            }}
          />
        </div>

        {/* Title */}
        <p style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#fff' }}>
          {step.title}
        </p>

        {/* Content */}
        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: 'rgba(255,255,255,0.68)' }}>
          {step.content}
        </p>

        {/* Nav */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 20,
          }}
        >
          {stepIndex > 0 ? (
            <button
              type="button"
              onClick={onPrev}
              style={{
                fontSize: 12,
                fontWeight: 500,
                color: 'rgba(255,255,255,0.6)',
                background: 'none',
                border: '1px solid rgba(255,255,255,0.15)',
                borderRadius: 8,
                padding: '6px 12px',
                cursor: 'pointer',
              }}
            >
              Back
            </button>
          ) : (
            <span />
          )}
          <button
            type="button"
            onClick={onNext}
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: '#1e1e1e',
              background: '#b9eb10',
              border: 'none',
              borderRadius: 8,
              padding: '6px 16px',
              cursor: 'pointer',
            }}
          >
            {stepIndex + 1 === total ? 'Done' : 'Next'}
          </button>
        </div>
      </div>
    </div>
  )
}
