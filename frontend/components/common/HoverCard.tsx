'use client'

import { useRef, useState, useCallback, useEffect, type ReactNode } from 'react'

type HoverCardProps = {
  trigger: ReactNode
  children: ReactNode
  className?: string
  align?: 'left' | 'center' | 'right'
  delay?: number
  maxWidth?: number
}

export function HoverCard({
  trigger,
  children,
  className = '',
  align = 'center',
  delay = 200,
  maxWidth = 320,
}: HoverCardProps) {
  const [open, setOpen] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLSpanElement>(null)

  const show = useCallback(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => setOpen(true), delay)
  }, [delay])

  const hide = useCallback(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    timeoutRef.current = setTimeout(() => setOpen(false), 100)
  }, [])

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [])

  const alignClass =
    align === 'left'
      ? 'left-0'
      : align === 'right'
        ? 'right-0'
        : 'left-1/2 -translate-x-1/2'

  return (
    <span
      ref={containerRef}
      className="relative inline-flex"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {trigger}
      {open ? (
        <span
          role="tooltip"
          className={`absolute top-full z-50 mt-1.5 rounded-lg border border-slate-200 bg-white p-3 text-xs leading-relaxed text-slate-700 shadow-lg ${alignClass} ${className}`}
          style={{ maxWidth }}
          onMouseEnter={show}
          onMouseLeave={hide}
        >
          {children}
        </span>
      ) : null}
    </span>
  )
}
