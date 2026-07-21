NAME = "Passthrough"


def build(tree):
    from nodebpy import geometry as g

    geometry = tree.inputs.geometry("Geometry")
    tree.outputs.geometry("Output") >> geometry
