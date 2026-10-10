#version 440
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 resolution;
    float softness;
    vec4 fillTop;
    vec4 fillBottom;
    vec4 rim;
};
layout(binding = 1) uniform sampler2D source;
void main() {
    float alpha=0.0;
    float weights=0.0;
    for(int i=-12;i<=12;++i) {
        float y=float(i)/4.0;
        float w=exp(-0.5*y*y);
        alpha += texture(source,qt_TexCoord0+vec2(0.0,y*softness/resolution.y)).a*w;
        weights+=w;
    }
    alpha/=weights;
    // liquid-gooey's contrast=18, intercept=-7 puts the merge at 5/12.
    // Derivatives anti-alias the threshold and provide a one-pixel inset rim.
    float threshold=5.0/12.0;
    float pixel=max(fwidth(alpha),0.001);
    float outer=smoothstep(threshold-pixel*0.5,threshold+pixel*0.5,alpha);
    float inner=smoothstep(threshold+pixel*0.5,threshold+pixel*1.5,alpha);
    vec4 color=mix(fillTop,fillBottom,clamp(qt_TexCoord0.y*2.0,0.0,1.0));
    fragColor=(color*inner+rim*(outer-inner))*qt_Opacity;
}
