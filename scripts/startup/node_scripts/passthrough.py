NAME = "Passthrough"
DESCRIPTION = "Pass the geometry through unchanged."


def build(tree, params):
    from nodebpy import geometry as g

    geometry = tree.inputs.geometry("Geometry")
    tree.outputs.geometry("Output") >> geometry
