#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 resolution;
    float softness;
};
layout(binding = 1) uniform sampler2D source;
void main() {
    float alpha = 0.0;
    float weights = 0.0;
    // Separable Gaussian; each pass covers three standard deviations.
    for (int i=-12; i<=12; ++i) {
        float x = float(i) / 4.0;
        float w = exp(-0.5*x*x);
        alpha += texture(source, qt_TexCoord0 + vec2(x*softness/resolution.x,0.0)).a*w;
        weights += w;
    }
    fragColor = vec4(alpha/weights) * qt_Opacity;
}
