NAME = "Emission Scale Ramp"

# Ported from /tmp/blendyt_review/sphere_perturbations.py's `emitted_scale`
# function (blendyt's `nodetree_script` DSL), translated to this repo's
# `nodebpy` DSL.
#
# Design change vs. the original (judgment call - see port report for full
# reasoning): the original read an INT `index_attribute` (an emission order)
# and computed `scale = clamp((ts - index * frame_delta) / frame_delta, 1,
# 100)`, i.e. it assumed emissions are evenly spaced `frame_delta` frames
# apart. That assumption doesn't hold for this repo's actual companion data
# source, constant_mass_emission_generator.py (CMET): CMET's whole point is
# *constant mass per sphere*, which generally means *uneven* time gaps
# between emissions (see its `emission_time` FLOAT point attribute, computed
# via PCHIP root-finding in constant_mass_core.py) - `sphere_index * frame_delta`
# would only reproduce the correct emission time if mass were emitted at a
# constant rate, which is precisely the case CMET exists to handle when it
# ISN'T true.
#
# So instead of an INT index attribute + frame_delta multiplication, this
# version reads a FLOAT attribute that already holds each element's own
# emission time in frame units directly (default name "emission_time" -
# CMET's own attribute name, see constant_mass_emission_generator.py's
# `_write_float_attribute(obj, "emission_time", emission_times)`), and
# computes `scale = clamp((current_frame - emission_time) / frame_delta,
# min_scale, max_scale)`. This is a strict generalization of the original
# formula (which is the special case emission_time == index * frame_delta)
# and stays generically reusable: point it at any FLOAT point/curve
# attribute holding a per-element start time in frame units, not just
# CMET's output specifically.
#
# Usage with CMET: this node group's Named Attribute node reads from
# whatever geometry is live at its call site - so use it inside a Geometry
# Nodes modifier on an object whose input geometry already carries CMET's
# "emission_time" attribute (e.g. via an Object Info node pointed at a CMET
# generator object, or on the CMET generator object's own further-downstream
# processing), then multiply/drive point scale (e.g. Instance on Points >
# Scale, or Set Point Radius) with this tree's "Scale" output.

PARAMS = {
    "time_attribute": {
        "type": "STRING",
        "default": "emission_time",
        "name": "Time Attribute",
        "description": (
            "FLOAT point/curve attribute holding each element's own "
            "emission time in frame units (e.g. constant_mass_emission_"
            "generator.py's 'emission_time' output)"
        ),
    },
}


def build(tree, params):
    from nodebpy import geometry as g

    time_attribute = params.get("time_attribute", "emission_time")

    frame_delta = tree.inputs.float(
        name="Frame Delta",
        default_value=24.0,
        description="Number of frames over which a point's scale ramps from Min Scale to Max Scale",
    )
    min_scale = tree.inputs.float(
        name="Min Scale",
        default_value=1.0,
        description="Scale value before/at a point's own emission time",
    )
    max_scale = tree.inputs.float(
        name="Max Scale",
        default_value=100.0,
        description="Scale value once a point has fully grown in",
    )

    current_frame = g.SceneTime().o.frame
    emission_time = g.NamedAttribute.float(name=time_attribute).o.attribute

    scale = g.Clamp(
        value=(current_frame - emission_time) / frame_delta,
        min=min_scale,
        max=max_scale,
    )

    tree.outputs.float(name="Scale") >> scale.o.result
