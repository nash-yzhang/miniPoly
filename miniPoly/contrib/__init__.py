"""Rig-specific implementations (contrib).

**Nothing in this package is part of the miniPoly framework contract.**

How this differs from `miniPoly/compiler/`:

    compiler/   Rig-agnostic compiler base classes. Must not contain mechanical
                geometry constants, must not contain a specific device's wire
                protocol, and must not contain any particular application's
                minion names.
    contrib/    Rig-specific implementations that nonetheless ship with the
                library. The API is not guaranteed to be stable.

Put new rig code that must ship with the library here, not in compiler/. Rig
code that has exactly one consumer belongs in that consumer's own repository
instead -- see the note below.

Currently empty. Its one occupant, `motorshield` (Adafruit Motor Shield serial
control), moved out entirely to CaImg_App.core.motorshield in the miniPolyApp
repository: miniPolyApp is its only consumer, so quarantining it here bought
nothing that moving it out did not buy more of. The same reasoning moved
`TISCameraCompiler` out of `miniPoly.compiler` (to CaImg_App.core.tiscamera);
the rig-agnostic half of that class stayed, as
`miniPoly.compiler.cameras.AbstractCameraCompiler`.
"""
