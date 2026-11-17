import{r as e}from"./rolldown-runtime-XKyaHtl9.js";import{C as t,x as n}from"./flow-AXKEwKnQ.js";function r(e){let t=e[0],n=e[1],r=e[2];return Math.sqrt(t*t+n*n+r*r)}function i(e,t){return e[0]=t[0],e[1]=t[1],e[2]=t[2],e}function a(e,t,n,r){return e[0]=t,e[1]=n,e[2]=r,e}function o(e,t,n){return e[0]=t[0]+n[0],e[1]=t[1]+n[1],e[2]=t[2]+n[2],e}function s(e,t,n){return e[0]=t[0]-n[0],e[1]=t[1]-n[1],e[2]=t[2]-n[2],e}function c(e,t,n){return e[0]=t[0]*n[0],e[1]=t[1]*n[1],e[2]=t[2]*n[2],e}function l(e,t,n){return e[0]=t[0]/n[0],e[1]=t[1]/n[1],e[2]=t[2]/n[2],e}function u(e,t,n){return e[0]=t[0]*n,e[1]=t[1]*n,e[2]=t[2]*n,e}function d(e,t){let n=t[0]-e[0],r=t[1]-e[1],i=t[2]-e[2];return Math.sqrt(n*n+r*r+i*i)}function f(e,t){let n=t[0]-e[0],r=t[1]-e[1],i=t[2]-e[2];return n*n+r*r+i*i}function p(e){let t=e[0],n=e[1],r=e[2];return t*t+n*n+r*r}function m(e,t){return e[0]=-t[0],e[1]=-t[1],e[2]=-t[2],e}function h(e,t){return e[0]=1/t[0],e[1]=1/t[1],e[2]=1/t[2],e}function g(e,t){let n=t[0],r=t[1],i=t[2],a=n*n+r*r+i*i;return a>0&&(a=1/Math.sqrt(a)),e[0]=t[0]*a,e[1]=t[1]*a,e[2]=t[2]*a,e}function _(e,t){return e[0]*t[0]+e[1]*t[1]+e[2]*t[2]}function v(e,t,n){let r=t[0],i=t[1],a=t[2],o=n[0],s=n[1],c=n[2];return e[0]=i*c-a*s,e[1]=a*o-r*c,e[2]=r*s-i*o,e}function y(e,t,n,r){let i=t[0],a=t[1],o=t[2];return e[0]=i+r*(n[0]-i),e[1]=a+r*(n[1]-a),e[2]=o+r*(n[2]-o),e}function b(e,t,n,r,i){let a=Math.exp(-r*i),o=t[0],s=t[1],c=t[2];return e[0]=n[0]+(o-n[0])*a,e[1]=n[1]+(s-n[1])*a,e[2]=n[2]+(c-n[2])*a,e}function x(e,t,n){let r=t[0],i=t[1],a=t[2],o=n[3]*r+n[7]*i+n[11]*a+n[15];return o||=1,e[0]=(n[0]*r+n[4]*i+n[8]*a+n[12])/o,e[1]=(n[1]*r+n[5]*i+n[9]*a+n[13])/o,e[2]=(n[2]*r+n[6]*i+n[10]*a+n[14])/o,e}function S(e,t,n){let r=t[0],i=t[1],a=t[2],o=n[3]*r+n[7]*i+n[11]*a+n[15];return o||=1,e[0]=(n[0]*r+n[4]*i+n[8]*a)/o,e[1]=(n[1]*r+n[5]*i+n[9]*a)/o,e[2]=(n[2]*r+n[6]*i+n[10]*a)/o,e}function C(e,t,n){let r=t[0],i=t[1],a=t[2];return e[0]=r*n[0]+i*n[3]+a*n[6],e[1]=r*n[1]+i*n[4]+a*n[7],e[2]=r*n[2]+i*n[5]+a*n[8],e}function w(e,t,n){let r=t[0],i=t[1],a=t[2],o=n[0],s=n[1],c=n[2],l=n[3],u=s*a-c*i,d=c*r-o*a,f=o*i-s*r,p=s*f-c*d,m=c*u-o*f,h=o*d-s*u,g=l*2;return u*=g,d*=g,f*=g,p*=2,m*=2,h*=2,e[0]=r+u+p,e[1]=i+d+m,e[2]=a+f+h,e}var T=(function(){let e=[0,0,0],t=[0,0,0];return function(n,r){i(e,n),i(t,r),g(e,e),g(t,t);let a=_(e,t);return a>1?0:a<-1?Math.PI:Math.acos(a)}})();function E(e,t){return e[0]===t[0]&&e[1]===t[1]&&e[2]===t[2]}var D=class e extends Array{constructor(e=0,t=e,n=e){return super(e,t,n),this}get x(){return this[0]}get y(){return this[1]}get z(){return this[2]}set x(e){this[0]=e}set y(e){this[1]=e}set z(e){this[2]=e}set(e,t=e,n=e){return e.length?this.copy(e):(a(this,e,t,n),this)}copy(e){return i(this,e),this}add(e,t){return t?o(this,e,t):o(this,this,e),this}sub(e,t){return t?s(this,e,t):s(this,this,e),this}multiply(e){return e.length?c(this,this,e):u(this,this,e),this}divide(e){return e.length?l(this,this,e):u(this,this,1/e),this}inverse(e=this){return h(this,e),this}len(){return r(this)}distance(e){return e?d(this,e):r(this)}squaredLen(){return p(this)}squaredDistance(e){return e?f(this,e):p(this)}negate(e=this){return m(this,e),this}cross(e,t){return t?v(this,e,t):v(this,this,e),this}scale(e){return u(this,this,e),this}normalize(){return g(this,this),this}dot(e){return _(this,e)}equals(e){return E(this,e)}applyMatrix3(e){return C(this,this,e),this}applyMatrix4(e){return x(this,this,e),this}scaleRotateMatrix4(e){return S(this,this,e),this}applyQuaternion(e){return w(this,this,e),this}angle(e){return T(this,e)}lerp(e,t){return y(this,this,e,t),this}smoothLerp(e,t,n){return b(this,this,e,t,n),this}clone(){return new e(this[0],this[1],this[2])}fromArray(e,t=0){return this[0]=e[t],this[1]=e[t+1],this[2]=e[t+2],this}toArray(e=[],t=0){return e[t]=this[0],e[t+1]=this[1],e[t+2]=this[2],e}transformDirection(e){let t=this[0],n=this[1],r=this[2];return this[0]=e[0]*t+e[4]*n+e[8]*r,this[1]=e[1]*t+e[5]*n+e[9]*r,this[2]=e[2]*t+e[6]*n+e[10]*r,this.normalize()}},O=new D,k=1,A=1,j=!1,M=class{constructor(e,t={}){e.canvas||console.error(`gl not passed as first argument to Geometry`),this.gl=e,this.attributes=t,this.id=k++,this.VAOs={},this.drawRange={start:0,count:0},this.instancedCount=0,this.gl.renderer.bindVertexArray(null),this.gl.renderer.currentGeometry=null,this.glState=this.gl.renderer.state;for(let e in t)this.addAttribute(e,t[e])}addAttribute(e,t){if(this.attributes[e]=t,t.id=A++,t.size=t.size||1,t.type=t.type||(t.data.constructor===Float32Array?this.gl.FLOAT:t.data.constructor===Uint16Array?this.gl.UNSIGNED_SHORT:this.gl.UNSIGNED_INT),t.target=e===`index`?this.gl.ELEMENT_ARRAY_BUFFER:this.gl.ARRAY_BUFFER,t.normalized=t.normalized||!1,t.stride=t.stride||0,t.offset=t.offset||0,t.count=t.count||(t.stride?t.data.byteLength/t.stride:t.data.length/t.size),t.divisor=t.instanced||0,t.needsUpdate=!1,t.usage=t.usage||this.gl.STATIC_DRAW,t.buffer||this.updateAttribute(t),t.divisor){if(this.isInstanced=!0,this.instancedCount&&this.instancedCount!==t.count*t.divisor)return console.warn(`geometry has multiple instanced buffers of different length`),this.instancedCount=Math.min(this.instancedCount,t.count*t.divisor);this.instancedCount=t.count*t.divisor}else e===`index`?this.drawRange.count=t.count:this.attributes.index||(this.drawRange.count=Math.max(this.drawRange.count,t.count))}updateAttribute(e){let t=!e.buffer;t&&(e.buffer=this.gl.createBuffer()),this.glState.boundBuffer!==e.buffer&&(this.gl.bindBuffer(e.target,e.buffer),this.glState.boundBuffer=e.buffer),t?this.gl.bufferData(e.target,e.data,e.usage):this.gl.bufferSubData(e.target,0,e.data),e.needsUpdate=!1}setIndex(e){this.addAttribute(`index`,e)}setDrawRange(e,t){this.drawRange.start=e,this.drawRange.count=t}setInstancedCount(e){this.instancedCount=e}createVAO(e){this.VAOs[e.attributeOrder]=this.gl.renderer.createVertexArray(),this.gl.renderer.bindVertexArray(this.VAOs[e.attributeOrder]),this.bindAttributes(e)}bindAttributes(e){e.attributeLocations.forEach((e,{name:t,type:n})=>{if(!this.attributes[t]){console.warn(`active attribute ${t} not being supplied`);return}let r=this.attributes[t];this.gl.bindBuffer(r.target,r.buffer),this.glState.boundBuffer=r.buffer;let i=1;n===35674&&(i=2),n===35675&&(i=3),n===35676&&(i=4);let a=r.size/i,o=i===1?0:i*i*4,s=i===1?0:i*4;for(let t=0;t<i;t++)this.gl.vertexAttribPointer(e+t,a,r.type,r.normalized,r.stride+o,r.offset+t*s),this.gl.enableVertexAttribArray(e+t),this.gl.renderer.vertexAttribDivisor(e+t,r.divisor)}),this.attributes.index&&this.gl.bindBuffer(this.gl.ELEMENT_ARRAY_BUFFER,this.attributes.index.buffer)}draw({program:e,mode:t=this.gl.TRIANGLES}){this.gl.renderer.currentGeometry!==`${this.id}_${e.attributeOrder}`&&(this.VAOs[e.attributeOrder]||this.createVAO(e),this.gl.renderer.bindVertexArray(this.VAOs[e.attributeOrder]),this.gl.renderer.currentGeometry=`${this.id}_${e.attributeOrder}`),e.attributeLocations.forEach((e,{name:t})=>{let n=this.attributes[t];n.needsUpdate&&this.updateAttribute(n)});let n=2;this.attributes.index?.type===this.gl.UNSIGNED_INT&&(n=4),this.isInstanced?this.attributes.index?this.gl.renderer.drawElementsInstanced(t,this.drawRange.count,this.attributes.index.type,this.attributes.index.offset+this.drawRange.start*n,this.instancedCount):this.gl.renderer.drawArraysInstanced(t,this.drawRange.start,this.drawRange.count,this.instancedCount):this.attributes.index?this.gl.drawElements(t,this.drawRange.count,this.attributes.index.type,this.attributes.index.offset+this.drawRange.start*n):this.gl.drawArrays(t,this.drawRange.start,this.drawRange.count)}getPosition(){let e=this.attributes.position;if(e.data)return e;if(!j)return console.warn(`No position buffer data found to compute bounds`),j=!0}computeBoundingBox(e){e||=this.getPosition();let t=e.data,n=e.size;this.bounds||={min:new D,max:new D,center:new D,scale:new D,radius:1/0};let r=this.bounds.min,i=this.bounds.max,a=this.bounds.center,o=this.bounds.scale;r.set(1/0),i.set(-1/0);for(let e=0,a=t.length;e<a;e+=n){let n=t[e],a=t[e+1],o=t[e+2];r.x=Math.min(n,r.x),r.y=Math.min(a,r.y),r.z=Math.min(o,r.z),i.x=Math.max(n,i.x),i.y=Math.max(a,i.y),i.z=Math.max(o,i.z)}o.sub(i,r),a.add(r,i).divide(2)}computeBoundingSphere(e){e||=this.getPosition();let t=e.data,n=e.size;this.bounds||this.computeBoundingBox(e);let r=0;for(let e=0,i=t.length;e<i;e+=n)O.fromArray(t,e),r=Math.max(r,this.bounds.center.squaredDistance(O));this.bounds.radius=Math.sqrt(r)}remove(){for(let e in this.VAOs)this.gl.renderer.deleteVertexArray(this.VAOs[e]),delete this.VAOs[e];for(let e in this.attributes)this.gl.deleteBuffer(this.attributes[e].buffer),delete this.attributes[e]}},ee=1,te={},ne=class{constructor(e,{vertex:t,fragment:n,uniforms:r={},transparent:i=!1,cullFace:a=e.BACK,frontFace:o=e.CCW,depthTest:s=!0,depthWrite:c=!0,depthFunc:l=e.LEQUAL}={}){e.canvas||console.error(`gl not passed as first argument to Program`),this.gl=e,this.uniforms=r,this.id=ee++,t||console.warn(`vertex shader not supplied`),n||console.warn(`fragment shader not supplied`),this.transparent=i,this.cullFace=a,this.frontFace=o,this.depthTest=s,this.depthWrite=c,this.depthFunc=l,this.blendFunc={},this.blendEquation={},this.stencilFunc={},this.stencilOp={},this.transparent&&!this.blendFunc.src&&(this.gl.renderer.premultipliedAlpha?this.setBlendFunc(this.gl.ONE,this.gl.ONE_MINUS_SRC_ALPHA):this.setBlendFunc(this.gl.SRC_ALPHA,this.gl.ONE_MINUS_SRC_ALPHA)),this.vertexShader=e.createShader(e.VERTEX_SHADER),this.fragmentShader=e.createShader(e.FRAGMENT_SHADER),this.program=e.createProgram(),e.attachShader(this.program,this.vertexShader),e.attachShader(this.program,this.fragmentShader),this.setShaders({vertex:t,fragment:n})}setShaders({vertex:e,fragment:t}){if(e&&(this.gl.shaderSource(this.vertexShader,e),this.gl.compileShader(this.vertexShader),this.gl.getShaderInfoLog(this.vertexShader)!==``&&console.warn(`${this.gl.getShaderInfoLog(this.vertexShader)}\nVertex Shader\n${ie(e)}`)),t&&(this.gl.shaderSource(this.fragmentShader,t),this.gl.compileShader(this.fragmentShader),this.gl.getShaderInfoLog(this.fragmentShader)!==``&&console.warn(`${this.gl.getShaderInfoLog(this.fragmentShader)}\nFragment Shader\n${ie(t)}`)),this.gl.linkProgram(this.program),!this.gl.getProgramParameter(this.program,this.gl.LINK_STATUS))return console.warn(this.gl.getProgramInfoLog(this.program));this.uniformLocations=new Map;let n=this.gl.getProgramParameter(this.program,this.gl.ACTIVE_UNIFORMS);for(let e=0;e<n;e++){let t=this.gl.getActiveUniform(this.program,e);this.uniformLocations.set(t,this.gl.getUniformLocation(this.program,t.name));let n=t.name.match(/(\w+)/g);t.uniformName=n[0],t.nameComponents=n.slice(1)}this.attributeLocations=new Map;let r=[],i=this.gl.getProgramParameter(this.program,this.gl.ACTIVE_ATTRIBUTES);for(let e=0;e<i;e++){let t=this.gl.getActiveAttrib(this.program,e),n=this.gl.getAttribLocation(this.program,t.name);n!==-1&&(r[n]=t.name,this.attributeLocations.set(t,n))}this.attributeOrder=r.join(``)}setBlendFunc(e,t,n,r){this.blendFunc.src=e,this.blendFunc.dst=t,this.blendFunc.srcAlpha=n,this.blendFunc.dstAlpha=r,e&&(this.transparent=!0)}setBlendEquation(e,t){this.blendEquation.modeRGB=e,this.blendEquation.modeAlpha=t}setStencilFunc(e,t,n){this.stencilRef=t,this.stencilFunc.func=e,this.stencilFunc.ref=t,this.stencilFunc.mask=n}setStencilOp(e,t,n){this.stencilOp.stencilFail=e,this.stencilOp.depthFail=t,this.stencilOp.depthPass=n}applyState(){this.depthTest?this.gl.renderer.enable(this.gl.DEPTH_TEST):this.gl.renderer.disable(this.gl.DEPTH_TEST),this.cullFace?this.gl.renderer.enable(this.gl.CULL_FACE):this.gl.renderer.disable(this.gl.CULL_FACE),this.blendFunc.src?this.gl.renderer.enable(this.gl.BLEND):this.gl.renderer.disable(this.gl.BLEND),this.cullFace&&this.gl.renderer.setCullFace(this.cullFace),this.gl.renderer.setFrontFace(this.frontFace),this.gl.renderer.setDepthMask(this.depthWrite),this.gl.renderer.setDepthFunc(this.depthFunc),this.blendFunc.src&&this.gl.renderer.setBlendFunc(this.blendFunc.src,this.blendFunc.dst,this.blendFunc.srcAlpha,this.blendFunc.dstAlpha),this.gl.renderer.setBlendEquation(this.blendEquation.modeRGB,this.blendEquation.modeAlpha),this.stencilFunc.func||this.stencilOp.stencilFail?this.gl.renderer.enable(this.gl.STENCIL_TEST):this.gl.renderer.disable(this.gl.STENCIL_TEST),this.gl.renderer.setStencilFunc(this.stencilFunc.func,this.stencilFunc.ref,this.stencilFunc.mask),this.gl.renderer.setStencilOp(this.stencilOp.stencilFail,this.stencilOp.depthFail,this.stencilOp.depthPass)}use({flipFaces:e=!1}={}){let t=-1;this.gl.renderer.state.currentProgram!==this.id&&(this.gl.useProgram(this.program),this.gl.renderer.state.currentProgram=this.id),this.uniformLocations.forEach((e,n)=>{let r=this.uniforms[n.uniformName];for(let e of n.nameComponents){if(!r)break;if(e in r)r=r[e];else if(Array.isArray(r.value))break;else{r=void 0;break}}if(!r)return ae(`Active uniform ${n.name} has not been supplied`);if(r&&r.value===void 0)return ae(`${n.name} uniform is missing a value parameter`);if(r.value.texture)return t+=1,r.value.update(t),re(this.gl,n.type,e,t);if(r.value.length&&r.value[0].texture){let i=[];return r.value.forEach(e=>{t+=1,e.update(t),i.push(t)}),re(this.gl,n.type,e,i)}re(this.gl,n.type,e,r.value)}),this.applyState(),e&&this.gl.renderer.setFrontFace(this.frontFace===this.gl.CCW?this.gl.CW:this.gl.CCW)}remove(){this.gl.deleteProgram(this.program)}};function re(e,t,n,r){r=r.length?N(r):r;let i=e.renderer.state.uniformLocations.get(n);if(r.length){if(i===void 0||i.length!==r.length)e.renderer.state.uniformLocations.set(n,r.slice(0));else{if(P(i,r))return;i.set?i.set(r):F(i,r),e.renderer.state.uniformLocations.set(n,i)}}else{if(i===r)return;e.renderer.state.uniformLocations.set(n,r)}switch(t){case 5126:return r.length?e.uniform1fv(n,r):e.uniform1f(n,r);case 35664:return e.uniform2fv(n,r);case 35665:return e.uniform3fv(n,r);case 35666:return e.uniform4fv(n,r);case 35670:case 5124:case 35678:case 36306:case 35680:case 36289:return r.length?e.uniform1iv(n,r):e.uniform1i(n,r);case 35671:case 35667:return e.uniform2iv(n,r);case 35672:case 35668:return e.uniform3iv(n,r);case 35673:case 35669:return e.uniform4iv(n,r);case 35674:return e.uniformMatrix2fv(n,!1,r);case 35675:return e.uniformMatrix3fv(n,!1,r);case 35676:return e.uniformMatrix4fv(n,!1,r)}}function ie(e){let t=e.split(`
`);for(let e=0;e<t.length;e++)t[e]=e+1+`: `+t[e];return t.join(`
`)}function N(e){let t=e.length,n=e[0].length;if(n===void 0)return e;let r=t*n,i=te[r];i||(te[r]=i=new Float32Array(r));for(let r=0;r<t;r++)i.set(e[r],r*n);return i}function P(e,t){if(e.length!==t.length)return!1;for(let n=0,r=e.length;n<r;n++)if(e[n]!==t[n])return!1;return!0}function F(e,t){for(let n=0,r=e.length;n<r;n++)e[n]=t[n]}var I=0;function ae(e){I>100||(console.warn(e),I++,I>100&&console.warn(`More than 100 program warnings - stopping logs.`))}var oe=new D,se=1,ce=class{constructor({canvas:e=document.createElement(`canvas`),width:t=300,height:n=150,dpr:r=1,alpha:i=!1,depth:a=!0,stencil:o=!1,antialias:s=!1,premultipliedAlpha:c=!1,preserveDrawingBuffer:l=!1,powerPreference:u=`default`,autoClear:d=!0,webgl:f=2}={}){let p={alpha:i,depth:a,stencil:o,antialias:s,premultipliedAlpha:c,preserveDrawingBuffer:l,powerPreference:u};this.dpr=r,this.alpha=i,this.color=!0,this.depth=a,this.stencil=o,this.premultipliedAlpha=c,this.autoClear=d,this.id=se++,f===2&&(this.gl=e.getContext(`webgl2`,p)),this.isWebgl2=!!this.gl,this.gl||=e.getContext(`webgl`,p),this.gl||console.error(`unable to create webgl context`),this.gl.renderer=this,this.setSize(t,n),this.state={},this.state.blendFunc={src:this.gl.ONE,dst:this.gl.ZERO},this.state.blendEquation={modeRGB:this.gl.FUNC_ADD},this.state.cullFace=!1,this.state.frontFace=this.gl.CCW,this.state.depthMask=!0,this.state.depthFunc=this.gl.LEQUAL,this.state.premultiplyAlpha=!1,this.state.flipY=!1,this.state.unpackAlignment=4,this.state.framebuffer=null,this.state.viewport={x:0,y:0,width:null,height:null},this.state.textureUnits=[],this.state.activeTextureUnit=0,this.state.boundBuffer=null,this.state.uniformLocations=new Map,this.state.currentProgram=null,this.extensions={},this.isWebgl2?(this.getExtension(`EXT_color_buffer_float`),this.getExtension(`OES_texture_float_linear`)):(this.getExtension(`OES_texture_float`),this.getExtension(`OES_texture_float_linear`),this.getExtension(`OES_texture_half_float`),this.getExtension(`OES_texture_half_float_linear`),this.getExtension(`OES_element_index_uint`),this.getExtension(`OES_standard_derivatives`),this.getExtension(`EXT_sRGB`),this.getExtension(`WEBGL_depth_texture`),this.getExtension(`WEBGL_draw_buffers`)),this.getExtension(`WEBGL_compressed_texture_astc`),this.getExtension(`EXT_texture_compression_bptc`),this.getExtension(`WEBGL_compressed_texture_s3tc`),this.getExtension(`WEBGL_compressed_texture_etc1`),this.getExtension(`WEBGL_compressed_texture_pvrtc`),this.getExtension(`WEBKIT_WEBGL_compressed_texture_pvrtc`),this.vertexAttribDivisor=this.getExtension(`ANGLE_instanced_arrays`,`vertexAttribDivisor`,`vertexAttribDivisorANGLE`),this.drawArraysInstanced=this.getExtension(`ANGLE_instanced_arrays`,`drawArraysInstanced`,`drawArraysInstancedANGLE`),this.drawElementsInstanced=this.getExtension(`ANGLE_instanced_arrays`,`drawElementsInstanced`,`drawElementsInstancedANGLE`),this.createVertexArray=this.getExtension(`OES_vertex_array_object`,`createVertexArray`,`createVertexArrayOES`),this.bindVertexArray=this.getExtension(`OES_vertex_array_object`,`bindVertexArray`,`bindVertexArrayOES`),this.deleteVertexArray=this.getExtension(`OES_vertex_array_object`,`deleteVertexArray`,`deleteVertexArrayOES`),this.drawBuffers=this.getExtension(`WEBGL_draw_buffers`,`drawBuffers`,`drawBuffersWEBGL`),this.parameters={},this.parameters.maxTextureUnits=this.gl.getParameter(this.gl.MAX_COMBINED_TEXTURE_IMAGE_UNITS),this.parameters.maxAnisotropy=this.getExtension(`EXT_texture_filter_anisotropic`)?this.gl.getParameter(this.getExtension(`EXT_texture_filter_anisotropic`).MAX_TEXTURE_MAX_ANISOTROPY_EXT):0}setSize(e,t){this.width=e,this.height=t,this.gl.canvas.width=e*this.dpr,this.gl.canvas.height=t*this.dpr,this.gl.canvas.style&&Object.assign(this.gl.canvas.style,{width:e+`px`,height:t+`px`})}setViewport(e,t,n=0,r=0){(this.state.viewport.width!==e||this.state.viewport.height!==t)&&(this.state.viewport.width=e,this.state.viewport.height=t,this.state.viewport.x=n,this.state.viewport.y=r,this.gl.viewport(n,r,e,t))}setScissor(e,t,n=0,r=0){this.gl.scissor(n,r,e,t)}enable(e){this.state[e]!==!0&&(this.gl.enable(e),this.state[e]=!0)}disable(e){this.state[e]!==!1&&(this.gl.disable(e),this.state[e]=!1)}setBlendFunc(e,t,n,r){(this.state.blendFunc.src!==e||this.state.blendFunc.dst!==t||this.state.blendFunc.srcAlpha!==n||this.state.blendFunc.dstAlpha!==r)&&(this.state.blendFunc.src=e,this.state.blendFunc.dst=t,this.state.blendFunc.srcAlpha=n,this.state.blendFunc.dstAlpha=r,n===void 0?this.gl.blendFunc(e,t):this.gl.blendFuncSeparate(e,t,n,r))}setBlendEquation(e,t){e||=this.gl.FUNC_ADD,(this.state.blendEquation.modeRGB!==e||this.state.blendEquation.modeAlpha!==t)&&(this.state.blendEquation.modeRGB=e,this.state.blendEquation.modeAlpha=t,t===void 0?this.gl.blendEquation(e):this.gl.blendEquationSeparate(e,t))}setCullFace(e){this.state.cullFace!==e&&(this.state.cullFace=e,this.gl.cullFace(e))}setFrontFace(e){this.state.frontFace!==e&&(this.state.frontFace=e,this.gl.frontFace(e))}setDepthMask(e){this.state.depthMask!==e&&(this.state.depthMask=e,this.gl.depthMask(e))}setDepthFunc(e){this.state.depthFunc!==e&&(this.state.depthFunc=e,this.gl.depthFunc(e))}setStencilMask(e){this.state.stencilMask!==e&&(this.state.stencilMask=e,this.gl.stencilMask(e))}setStencilFunc(e,t,n){(this.state.stencilFunc!==e||this.state.stencilRef!==t||this.state.stencilFuncMask!==n)&&(this.state.stencilFunc=e||this.gl.ALWAYS,this.state.stencilRef=t||0,this.state.stencilFuncMask=n||0,this.gl.stencilFunc(e||this.gl.ALWAYS,t||0,n||0))}setStencilOp(e,t,n){(this.state.stencilFail!==e||this.state.stencilDepthFail!==t||this.state.stencilDepthPass!==n)&&(this.state.stencilFail=e,this.state.stencilDepthFail=t,this.state.stencilDepthPass=n,this.gl.stencilOp(e,t,n))}activeTexture(e){this.state.activeTextureUnit!==e&&(this.state.activeTextureUnit=e,this.gl.activeTexture(this.gl.TEXTURE0+e))}bindFramebuffer({target:e=this.gl.FRAMEBUFFER,buffer:t=null}={}){this.state.framebuffer!==t&&(this.state.framebuffer=t,this.gl.bindFramebuffer(e,t))}getExtension(e,t,n){return t&&this.gl[t]?this.gl[t].bind(this.gl):(this.extensions[e]||(this.extensions[e]=this.gl.getExtension(e)),t?this.extensions[e]?this.extensions[e][n].bind(this.extensions[e]):null:this.extensions[e])}sortOpaque(e,t){return e.renderOrder===t.renderOrder?e.program.id===t.program.id?e.zDepth===t.zDepth?t.id-e.id:e.zDepth-t.zDepth:e.program.id-t.program.id:e.renderOrder-t.renderOrder}sortTransparent(e,t){return e.renderOrder===t.renderOrder?e.zDepth===t.zDepth?t.id-e.id:t.zDepth-e.zDepth:e.renderOrder-t.renderOrder}sortUI(e,t){return e.renderOrder===t.renderOrder?e.program.id===t.program.id?t.id-e.id:e.program.id-t.program.id:e.renderOrder-t.renderOrder}getRenderList({scene:e,camera:t,frustumCull:n,sort:r}){let i=[];if(t&&n&&t.updateFrustum(),e.traverse(e=>{if(!e.visible)return!0;e.draw&&(n&&e.frustumCulled&&t&&!t.frustumIntersectsMesh(e)||i.push(e))}),r){let e=[],n=[],r=[];i.forEach(i=>{i.program.transparent?i.program.depthTest?n.push(i):r.push(i):e.push(i),i.zDepth=0,i.renderOrder===0&&i.program.depthTest&&t&&(i.worldMatrix.getTranslation(oe),oe.applyMatrix4(t.projectionViewMatrix),i.zDepth=oe.z)}),e.sort(this.sortOpaque),n.sort(this.sortTransparent),r.sort(this.sortUI),i=e.concat(n,r)}return i}render({scene:e,camera:t,target:n=null,update:r=!0,sort:i=!0,frustumCull:a=!0,clear:o}){n===null?(this.bindFramebuffer(),this.setViewport(this.width*this.dpr,this.height*this.dpr)):(this.bindFramebuffer(n),this.setViewport(n.width,n.height)),(o||this.autoClear&&o!==!1)&&(this.depth&&(!n||n.depth)&&(this.enable(this.gl.DEPTH_TEST),this.setDepthMask(!0)),(this.stencil||!n||n.stencil)&&(this.enable(this.gl.STENCIL_TEST),this.setStencilMask(255)),this.gl.clear((this.color?this.gl.COLOR_BUFFER_BIT:0)|(this.depth?this.gl.DEPTH_BUFFER_BIT:0)|(this.stencil?this.gl.STENCIL_BUFFER_BIT:0))),r&&e.updateMatrixWorld(),t&&t.updateMatrixWorld(),this.getRenderList({scene:e,camera:t,frustumCull:a,sort:i}).forEach(e=>{e.draw({camera:t})})}};function le(e,t){return e[0]=t[0],e[1]=t[1],e[2]=t[2],e[3]=t[3],e}function L(e,t,n,r,i){return e[0]=t,e[1]=n,e[2]=r,e[3]=i,e}function ue(e,t){let n=t[0],r=t[1],i=t[2],a=t[3],o=n*n+r*r+i*i+a*a;return o>0&&(o=1/Math.sqrt(o)),e[0]=n*o,e[1]=r*o,e[2]=i*o,e[3]=a*o,e}function de(e,t){return e[0]*t[0]+e[1]*t[1]+e[2]*t[2]+e[3]*t[3]}function R(e){return e[0]=0,e[1]=0,e[2]=0,e[3]=1,e}function z(e,t,n){n*=.5;let r=Math.sin(n);return e[0]=r*t[0],e[1]=r*t[1],e[2]=r*t[2],e[3]=Math.cos(n),e}function fe(e,t,n){let r=t[0],i=t[1],a=t[2],o=t[3],s=n[0],c=n[1],l=n[2],u=n[3];return e[0]=r*u+o*s+i*l-a*c,e[1]=i*u+o*c+a*s-r*l,e[2]=a*u+o*l+r*c-i*s,e[3]=o*u-r*s-i*c-a*l,e}function B(e,t,n){n*=.5;let r=t[0],i=t[1],a=t[2],o=t[3],s=Math.sin(n),c=Math.cos(n);return e[0]=r*c+o*s,e[1]=i*c+a*s,e[2]=a*c-i*s,e[3]=o*c-r*s,e}function pe(e,t,n){n*=.5;let r=t[0],i=t[1],a=t[2],o=t[3],s=Math.sin(n),c=Math.cos(n);return e[0]=r*c-a*s,e[1]=i*c+o*s,e[2]=a*c+r*s,e[3]=o*c-i*s,e}function V(e,t,n){n*=.5;let r=t[0],i=t[1],a=t[2],o=t[3],s=Math.sin(n),c=Math.cos(n);return e[0]=r*c+i*s,e[1]=i*c-r*s,e[2]=a*c+o*s,e[3]=o*c-a*s,e}function H(e,t,n,r){let i=t[0],a=t[1],o=t[2],s=t[3],c=n[0],l=n[1],u=n[2],d=n[3],f,p,m,h,g;return p=i*c+a*l+o*u+s*d,p<0&&(p=-p,c=-c,l=-l,u=-u,d=-d),1-p>1e-6?(f=Math.acos(p),m=Math.sin(f),h=Math.sin((1-r)*f)/m,g=Math.sin(r*f)/m):(h=1-r,g=r),e[0]=h*i+g*c,e[1]=h*a+g*l,e[2]=h*o+g*u,e[3]=h*s+g*d,e}function U(e,t){let n=t[0],r=t[1],i=t[2],a=t[3],o=n*n+r*r+i*i+a*a,s=o?1/o:0;return e[0]=-n*s,e[1]=-r*s,e[2]=-i*s,e[3]=a*s,e}function W(e,t){return e[0]=-t[0],e[1]=-t[1],e[2]=-t[2],e[3]=t[3],e}function G(e,t){let n=t[0]+t[4]+t[8],r;if(n>0)r=Math.sqrt(n+1),e[3]=.5*r,r=.5/r,e[0]=(t[5]-t[7])*r,e[1]=(t[6]-t[2])*r,e[2]=(t[1]-t[3])*r;else{let n=0;t[4]>t[0]&&(n=1),t[8]>t[n*3+n]&&(n=2);let i=(n+1)%3,a=(n+2)%3;r=Math.sqrt(t[n*3+n]-t[i*3+i]-t[a*3+a]+1),e[n]=.5*r,r=.5/r,e[3]=(t[i*3+a]-t[a*3+i])*r,e[i]=(t[i*3+n]+t[n*3+i])*r,e[a]=(t[a*3+n]+t[n*3+a])*r}return e}function me(e,t,n=`YXZ`){let r=Math.sin(t[0]*.5),i=Math.cos(t[0]*.5),a=Math.sin(t[1]*.5),o=Math.cos(t[1]*.5),s=Math.sin(t[2]*.5),c=Math.cos(t[2]*.5);return n===`XYZ`?(e[0]=r*o*c+i*a*s,e[1]=i*a*c-r*o*s,e[2]=i*o*s+r*a*c,e[3]=i*o*c-r*a*s):n===`YXZ`?(e[0]=r*o*c+i*a*s,e[1]=i*a*c-r*o*s,e[2]=i*o*s-r*a*c,e[3]=i*o*c+r*a*s):n===`ZXY`?(e[0]=r*o*c-i*a*s,e[1]=i*a*c+r*o*s,e[2]=i*o*s+r*a*c,e[3]=i*o*c-r*a*s):n===`ZYX`?(e[0]=r*o*c-i*a*s,e[1]=i*a*c+r*o*s,e[2]=i*o*s-r*a*c,e[3]=i*o*c+r*a*s):n===`YZX`?(e[0]=r*o*c+i*a*s,e[1]=i*a*c+r*o*s,e[2]=i*o*s-r*a*c,e[3]=i*o*c-r*a*s):n===`XZY`&&(e[0]=r*o*c-i*a*s,e[1]=i*a*c-r*o*s,e[2]=i*o*s+r*a*c,e[3]=i*o*c+r*a*s),e}var he=le,ge=L,_e=de,ve=ue,K=class extends Array{constructor(e=0,t=0,n=0,r=1){super(e,t,n,r),this.onChange=()=>{},this._target=this;let i=[`0`,`1`,`2`,`3`];return new Proxy(this,{set(e,t){let n=Reflect.set(...arguments);return n&&i.includes(t)&&e.onChange(),n}})}get x(){return this[0]}get y(){return this[1]}get z(){return this[2]}get w(){return this[3]}set x(e){this._target[0]=e,this.onChange()}set y(e){this._target[1]=e,this.onChange()}set z(e){this._target[2]=e,this.onChange()}set w(e){this._target[3]=e,this.onChange()}identity(){return R(this._target),this.onChange(),this}set(e,t,n,r){return e.length?this.copy(e):(ge(this._target,e,t,n,r),this.onChange(),this)}rotateX(e){return B(this._target,this._target,e),this.onChange(),this}rotateY(e){return pe(this._target,this._target,e),this.onChange(),this}rotateZ(e){return V(this._target,this._target,e),this.onChange(),this}inverse(e=this._target){return U(this._target,e),this.onChange(),this}conjugate(e=this._target){return W(this._target,e),this.onChange(),this}copy(e){return he(this._target,e),this.onChange(),this}normalize(e=this._target){return ve(this._target,e),this.onChange(),this}multiply(e,t){return t?fe(this._target,e,t):fe(this._target,this._target,e),this.onChange(),this}dot(e){return _e(this._target,e)}fromMatrix3(e){return G(this._target,e),this.onChange(),this}fromEuler(e,t){return me(this._target,e,e.order),t||this.onChange(),this}fromAxisAngle(e,t){return z(this._target,e,t),this.onChange(),this}slerp(e,t){return H(this._target,this._target,e,t),this.onChange(),this}fromArray(e,t=0){return this._target[0]=e[t],this._target[1]=e[t+1],this._target[2]=e[t+2],this._target[3]=e[t+3],this.onChange(),this}toArray(e=[],t=0){return e[t]=this[0],e[t+1]=this[1],e[t+2]=this[2],e[t+3]=this[3],e}},q=1e-6;function ye(e,t){return e[0]=t[0],e[1]=t[1],e[2]=t[2],e[3]=t[3],e[4]=t[4],e[5]=t[5],e[6]=t[6],e[7]=t[7],e[8]=t[8],e[9]=t[9],e[10]=t[10],e[11]=t[11],e[12]=t[12],e[13]=t[13],e[14]=t[14],e[15]=t[15],e}function be(e,t,n,r,i,a,o,s,c,l,u,d,f,p,m,h,g){return e[0]=t,e[1]=n,e[2]=r,e[3]=i,e[4]=a,e[5]=o,e[6]=s,e[7]=c,e[8]=l,e[9]=u,e[10]=d,e[11]=f,e[12]=p,e[13]=m,e[14]=h,e[15]=g,e}function J(e){return e[0]=1,e[1]=0,e[2]=0,e[3]=0,e[4]=0,e[5]=1,e[6]=0,e[7]=0,e[8]=0,e[9]=0,e[10]=1,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,e}function xe(e,t){let n=t[0],r=t[1],i=t[2],a=t[3],o=t[4],s=t[5],c=t[6],l=t[7],u=t[8],d=t[9],f=t[10],p=t[11],m=t[12],h=t[13],g=t[14],_=t[15],v=n*s-r*o,y=n*c-i*o,b=n*l-a*o,x=r*c-i*s,S=r*l-a*s,C=i*l-a*c,w=u*h-d*m,T=u*g-f*m,E=u*_-p*m,D=d*g-f*h,O=d*_-p*h,k=f*_-p*g,A=v*k-y*O+b*D+x*E-S*T+C*w;return A?(A=1/A,e[0]=(s*k-c*O+l*D)*A,e[1]=(i*O-r*k-a*D)*A,e[2]=(h*C-g*S+_*x)*A,e[3]=(f*S-d*C-p*x)*A,e[4]=(c*E-o*k-l*T)*A,e[5]=(n*k-i*E+a*T)*A,e[6]=(g*b-m*C-_*y)*A,e[7]=(u*C-f*b+p*y)*A,e[8]=(o*O-s*E+l*w)*A,e[9]=(r*E-n*O-a*w)*A,e[10]=(m*S-h*b+_*v)*A,e[11]=(d*b-u*S-p*v)*A,e[12]=(s*T-o*D-c*w)*A,e[13]=(n*D-r*T+i*w)*A,e[14]=(h*y-m*x-g*v)*A,e[15]=(u*x-d*y+f*v)*A,e):null}function Y(e){let t=e[0],n=e[1],r=e[2],i=e[3],a=e[4],o=e[5],s=e[6],c=e[7],l=e[8],u=e[9],d=e[10],f=e[11],p=e[12],m=e[13],h=e[14],g=e[15],_=t*o-n*a,v=t*s-r*a,y=t*c-i*a,b=n*s-r*o,x=n*c-i*o,S=r*c-i*s,C=l*m-u*p,w=l*h-d*p,T=l*g-f*p,E=u*h-d*m,D=u*g-f*m;return _*(d*g-f*h)-v*D+y*E+b*T-x*w+S*C}function Se(e,t,n){let r=t[0],i=t[1],a=t[2],o=t[3],s=t[4],c=t[5],l=t[6],u=t[7],d=t[8],f=t[9],p=t[10],m=t[11],h=t[12],g=t[13],_=t[14],v=t[15],y=n[0],b=n[1],x=n[2],S=n[3];return e[0]=y*r+b*s+x*d+S*h,e[1]=y*i+b*c+x*f+S*g,e[2]=y*a+b*l+x*p+S*_,e[3]=y*o+b*u+x*m+S*v,y=n[4],b=n[5],x=n[6],S=n[7],e[4]=y*r+b*s+x*d+S*h,e[5]=y*i+b*c+x*f+S*g,e[6]=y*a+b*l+x*p+S*_,e[7]=y*o+b*u+x*m+S*v,y=n[8],b=n[9],x=n[10],S=n[11],e[8]=y*r+b*s+x*d+S*h,e[9]=y*i+b*c+x*f+S*g,e[10]=y*a+b*l+x*p+S*_,e[11]=y*o+b*u+x*m+S*v,y=n[12],b=n[13],x=n[14],S=n[15],e[12]=y*r+b*s+x*d+S*h,e[13]=y*i+b*c+x*f+S*g,e[14]=y*a+b*l+x*p+S*_,e[15]=y*o+b*u+x*m+S*v,e}function Ce(e,t,n){let r=n[0],i=n[1],a=n[2],o,s,c,l,u,d,f,p,m,h,g,_;return t===e?(e[12]=t[0]*r+t[4]*i+t[8]*a+t[12],e[13]=t[1]*r+t[5]*i+t[9]*a+t[13],e[14]=t[2]*r+t[6]*i+t[10]*a+t[14],e[15]=t[3]*r+t[7]*i+t[11]*a+t[15]):(o=t[0],s=t[1],c=t[2],l=t[3],u=t[4],d=t[5],f=t[6],p=t[7],m=t[8],h=t[9],g=t[10],_=t[11],e[0]=o,e[1]=s,e[2]=c,e[3]=l,e[4]=u,e[5]=d,e[6]=f,e[7]=p,e[8]=m,e[9]=h,e[10]=g,e[11]=_,e[12]=o*r+u*i+m*a+t[12],e[13]=s*r+d*i+h*a+t[13],e[14]=c*r+f*i+g*a+t[14],e[15]=l*r+p*i+_*a+t[15]),e}function we(e,t,n){let r=n[0],i=n[1],a=n[2];return e[0]=t[0]*r,e[1]=t[1]*r,e[2]=t[2]*r,e[3]=t[3]*r,e[4]=t[4]*i,e[5]=t[5]*i,e[6]=t[6]*i,e[7]=t[7]*i,e[8]=t[8]*a,e[9]=t[9]*a,e[10]=t[10]*a,e[11]=t[11]*a,e[12]=t[12],e[13]=t[13],e[14]=t[14],e[15]=t[15],e}function Te(e,t,n,r){let i=r[0],a=r[1],o=r[2],s=Math.hypot(i,a,o),c,l,u,d,f,p,m,h,g,_,v,y,b,x,S,C,w,T,E,D,O,k,A,j;return Math.abs(s)<q?null:(s=1/s,i*=s,a*=s,o*=s,c=Math.sin(n),l=Math.cos(n),u=1-l,d=t[0],f=t[1],p=t[2],m=t[3],h=t[4],g=t[5],_=t[6],v=t[7],y=t[8],b=t[9],x=t[10],S=t[11],C=i*i*u+l,w=a*i*u+o*c,T=o*i*u-a*c,E=i*a*u-o*c,D=a*a*u+l,O=o*a*u+i*c,k=i*o*u+a*c,A=a*o*u-i*c,j=o*o*u+l,e[0]=d*C+h*w+y*T,e[1]=f*C+g*w+b*T,e[2]=p*C+_*w+x*T,e[3]=m*C+v*w+S*T,e[4]=d*E+h*D+y*O,e[5]=f*E+g*D+b*O,e[6]=p*E+_*D+x*O,e[7]=m*E+v*D+S*O,e[8]=d*k+h*A+y*j,e[9]=f*k+g*A+b*j,e[10]=p*k+_*A+x*j,e[11]=m*k+v*A+S*j,t!==e&&(e[12]=t[12],e[13]=t[13],e[14]=t[14],e[15]=t[15]),e)}function Ee(e,t){return e[0]=t[12],e[1]=t[13],e[2]=t[14],e}function De(e,t){let n=t[0],r=t[1],i=t[2],a=t[4],o=t[5],s=t[6],c=t[8],l=t[9],u=t[10];return e[0]=Math.hypot(n,r,i),e[1]=Math.hypot(a,o,s),e[2]=Math.hypot(c,l,u),e}function Oe(e){let t=e[0],n=e[1],r=e[2],i=e[4],a=e[5],o=e[6],s=e[8],c=e[9],l=e[10],u=t*t+n*n+r*r,d=i*i+a*a+o*o,f=s*s+c*c+l*l;return Math.sqrt(Math.max(u,d,f))}var ke=(function(){let e=[1,1,1];return function(t,n){let r=e;De(r,n);let i=1/r[0],a=1/r[1],o=1/r[2],s=n[0]*i,c=n[1]*a,l=n[2]*o,u=n[4]*i,d=n[5]*a,f=n[6]*o,p=n[8]*i,m=n[9]*a,h=n[10]*o,g=s+d+h,_=0;return g>0?(_=Math.sqrt(g+1)*2,t[3]=.25*_,t[0]=(f-m)/_,t[1]=(p-l)/_,t[2]=(c-u)/_):s>d&&s>h?(_=Math.sqrt(1+s-d-h)*2,t[3]=(f-m)/_,t[0]=.25*_,t[1]=(c+u)/_,t[2]=(p+l)/_):d>h?(_=Math.sqrt(1+d-s-h)*2,t[3]=(p-l)/_,t[0]=(c+u)/_,t[1]=.25*_,t[2]=(f+m)/_):(_=Math.sqrt(1+h-s-d)*2,t[3]=(c-u)/_,t[0]=(p+l)/_,t[1]=(f+m)/_,t[2]=.25*_),t}})();function Ae(e,t,n,i){let a=r([e[0],e[1],e[2]]),o=r([e[4],e[5],e[6]]),s=r([e[8],e[9],e[10]]);Y(e)<0&&(a=-a),n[0]=e[12],n[1]=e[13],n[2]=e[14];let c=e.slice(),l=1/a,u=1/o,d=1/s;c[0]*=l,c[1]*=l,c[2]*=l,c[4]*=u,c[5]*=u,c[6]*=u,c[8]*=d,c[9]*=d,c[10]*=d,ke(t,c),i[0]=a,i[1]=o,i[2]=s}function je(e,t,n,r){let i=e,a=t[0],o=t[1],s=t[2],c=t[3],l=a+a,u=o+o,d=s+s,f=a*l,p=a*u,m=a*d,h=o*u,g=o*d,_=s*d,v=c*l,y=c*u,b=c*d,x=r[0],S=r[1],C=r[2];return i[0]=(1-(h+_))*x,i[1]=(p+b)*x,i[2]=(m-y)*x,i[3]=0,i[4]=(p-b)*S,i[5]=(1-(f+_))*S,i[6]=(g+v)*S,i[7]=0,i[8]=(m+y)*C,i[9]=(g-v)*C,i[10]=(1-(f+h))*C,i[11]=0,i[12]=n[0],i[13]=n[1],i[14]=n[2],i[15]=1,i}function Me(e,t){let n=t[0],r=t[1],i=t[2],a=t[3],o=n+n,s=r+r,c=i+i,l=n*o,u=r*o,d=r*s,f=i*o,p=i*s,m=i*c,h=a*o,g=a*s,_=a*c;return e[0]=1-d-m,e[1]=u+_,e[2]=f-g,e[3]=0,e[4]=u-_,e[5]=1-l-m,e[6]=p+h,e[7]=0,e[8]=f+g,e[9]=p-h,e[10]=1-l-d,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,e}function Ne(e,t,n,r,i){let a=1/Math.tan(t/2),o=1/(r-i);return e[0]=a/n,e[1]=0,e[2]=0,e[3]=0,e[4]=0,e[5]=a,e[6]=0,e[7]=0,e[8]=0,e[9]=0,e[10]=(i+r)*o,e[11]=-1,e[12]=0,e[13]=0,e[14]=2*i*r*o,e[15]=0,e}function Pe(e,t,n,r,i,a,o){let s=1/(t-n),c=1/(r-i),l=1/(a-o);return e[0]=-2*s,e[1]=0,e[2]=0,e[3]=0,e[4]=0,e[5]=-2*c,e[6]=0,e[7]=0,e[8]=0,e[9]=0,e[10]=2*l,e[11]=0,e[12]=(t+n)*s,e[13]=(i+r)*c,e[14]=(o+a)*l,e[15]=1,e}function Fe(e,t,n,r){let i=t[0],a=t[1],o=t[2],s=r[0],c=r[1],l=r[2],u=i-n[0],d=a-n[1],f=o-n[2],p=u*u+d*d+f*f;p===0?f=1:(p=1/Math.sqrt(p),u*=p,d*=p,f*=p);let m=c*f-l*d,h=l*u-s*f,g=s*d-c*u;return p=m*m+h*h+g*g,p===0&&(l?s+=1e-6:c?l+=1e-6:c+=1e-6,m=c*f-l*d,h=l*u-s*f,g=s*d-c*u,p=m*m+h*h+g*g),p=1/Math.sqrt(p),m*=p,h*=p,g*=p,e[0]=m,e[1]=h,e[2]=g,e[3]=0,e[4]=d*g-f*h,e[5]=f*m-u*g,e[6]=u*h-d*m,e[7]=0,e[8]=u,e[9]=d,e[10]=f,e[11]=0,e[12]=i,e[13]=a,e[14]=o,e[15]=1,e}function Ie(e,t,n){return e[0]=t[0]+n[0],e[1]=t[1]+n[1],e[2]=t[2]+n[2],e[3]=t[3]+n[3],e[4]=t[4]+n[4],e[5]=t[5]+n[5],e[6]=t[6]+n[6],e[7]=t[7]+n[7],e[8]=t[8]+n[8],e[9]=t[9]+n[9],e[10]=t[10]+n[10],e[11]=t[11]+n[11],e[12]=t[12]+n[12],e[13]=t[13]+n[13],e[14]=t[14]+n[14],e[15]=t[15]+n[15],e}function Le(e,t,n){return e[0]=t[0]-n[0],e[1]=t[1]-n[1],e[2]=t[2]-n[2],e[3]=t[3]-n[3],e[4]=t[4]-n[4],e[5]=t[5]-n[5],e[6]=t[6]-n[6],e[7]=t[7]-n[7],e[8]=t[8]-n[8],e[9]=t[9]-n[9],e[10]=t[10]-n[10],e[11]=t[11]-n[11],e[12]=t[12]-n[12],e[13]=t[13]-n[13],e[14]=t[14]-n[14],e[15]=t[15]-n[15],e}function Re(e,t,n){return e[0]=t[0]*n,e[1]=t[1]*n,e[2]=t[2]*n,e[3]=t[3]*n,e[4]=t[4]*n,e[5]=t[5]*n,e[6]=t[6]*n,e[7]=t[7]*n,e[8]=t[8]*n,e[9]=t[9]*n,e[10]=t[10]*n,e[11]=t[11]*n,e[12]=t[12]*n,e[13]=t[13]*n,e[14]=t[14]*n,e[15]=t[15]*n,e}var ze=class extends Array{constructor(e=1,t=0,n=0,r=0,i=0,a=1,o=0,s=0,c=0,l=0,u=1,d=0,f=0,p=0,m=0,h=1){return super(e,t,n,r,i,a,o,s,c,l,u,d,f,p,m,h),this}get x(){return this[12]}get y(){return this[13]}get z(){return this[14]}get w(){return this[15]}set x(e){this[12]=e}set y(e){this[13]=e}set z(e){this[14]=e}set w(e){this[15]=e}set(e,t,n,r,i,a,o,s,c,l,u,d,f,p,m,h){return e.length?this.copy(e):(be(this,e,t,n,r,i,a,o,s,c,l,u,d,f,p,m,h),this)}translate(e,t=this){return Ce(this,t,e),this}rotate(e,t,n=this){return Te(this,n,e,t),this}scale(e,t=this){return we(this,t,typeof e==`number`?[e,e,e]:e),this}add(e,t){return t?Ie(this,e,t):Ie(this,this,e),this}sub(e,t){return t?Le(this,e,t):Le(this,this,e),this}multiply(e,t){return e.length?t?Se(this,e,t):Se(this,this,e):Re(this,this,e),this}identity(){return J(this),this}copy(e){return ye(this,e),this}fromPerspective({fov:e,aspect:t,near:n,far:r}={}){return Ne(this,e,t,n,r),this}fromOrthogonal({left:e,right:t,bottom:n,top:r,near:i,far:a}){return Pe(this,e,t,n,r,i,a),this}fromQuaternion(e){return Me(this,e),this}setPosition(e){return this.x=e[0],this.y=e[1],this.z=e[2],this}inverse(e=this){return xe(this,e),this}compose(e,t,n){return je(this,e,t,n),this}decompose(e,t,n){return Ae(this,e,t,n),this}getRotation(e){return ke(e,this),this}getTranslation(e){return Ee(e,this),this}getScaling(e){return De(e,this),this}getMaxScaleOnAxis(){return Oe(this)}lookAt(e,t,n){return Fe(this,e,t,n),this}determinant(){return Y(this)}fromArray(e,t=0){return this[0]=e[t],this[1]=e[t+1],this[2]=e[t+2],this[3]=e[t+3],this[4]=e[t+4],this[5]=e[t+5],this[6]=e[t+6],this[7]=e[t+7],this[8]=e[t+8],this[9]=e[t+9],this[10]=e[t+10],this[11]=e[t+11],this[12]=e[t+12],this[13]=e[t+13],this[14]=e[t+14],this[15]=e[t+15],this}toArray(e=[],t=0){return e[t]=this[0],e[t+1]=this[1],e[t+2]=this[2],e[t+3]=this[3],e[t+4]=this[4],e[t+5]=this[5],e[t+6]=this[6],e[t+7]=this[7],e[t+8]=this[8],e[t+9]=this[9],e[t+10]=this[10],e[t+11]=this[11],e[t+12]=this[12],e[t+13]=this[13],e[t+14]=this[14],e[t+15]=this[15],e}};function Be(e,t,n=`YXZ`){return n===`XYZ`?(e[1]=Math.asin(Math.min(Math.max(t[8],-1),1)),Math.abs(t[8])<.99999?(e[0]=Math.atan2(-t[9],t[10]),e[2]=Math.atan2(-t[4],t[0])):(e[0]=Math.atan2(t[6],t[5]),e[2]=0)):n===`YXZ`?(e[0]=Math.asin(-Math.min(Math.max(t[9],-1),1)),Math.abs(t[9])<.99999?(e[1]=Math.atan2(t[8],t[10]),e[2]=Math.atan2(t[1],t[5])):(e[1]=Math.atan2(-t[2],t[0]),e[2]=0)):n===`ZXY`?(e[0]=Math.asin(Math.min(Math.max(t[6],-1),1)),Math.abs(t[6])<.99999?(e[1]=Math.atan2(-t[2],t[10]),e[2]=Math.atan2(-t[4],t[5])):(e[1]=0,e[2]=Math.atan2(t[1],t[0]))):n===`ZYX`?(e[1]=Math.asin(-Math.min(Math.max(t[2],-1),1)),Math.abs(t[2])<.99999?(e[0]=Math.atan2(t[6],t[10]),e[2]=Math.atan2(t[1],t[0])):(e[0]=0,e[2]=Math.atan2(-t[4],t[5]))):n===`YZX`?(e[2]=Math.asin(Math.min(Math.max(t[1],-1),1)),Math.abs(t[1])<.99999?(e[0]=Math.atan2(-t[9],t[5]),e[1]=Math.atan2(-t[2],t[0])):(e[0]=0,e[1]=Math.atan2(t[8],t[10]))):n===`XZY`&&(e[2]=Math.asin(-Math.min(Math.max(t[4],-1),1)),Math.abs(t[4])<.99999?(e[0]=Math.atan2(t[6],t[5]),e[1]=Math.atan2(t[8],t[0])):(e[0]=Math.atan2(-t[9],t[10]),e[1]=0)),e}var Ve=new ze,He=class extends Array{constructor(e=0,t=e,n=e,r=`YXZ`){super(e,t,n),this.order=r,this.onChange=()=>{},this._target=this;let i=[`0`,`1`,`2`];return new Proxy(this,{set(e,t){let n=Reflect.set(...arguments);return n&&i.includes(t)&&e.onChange(),n}})}get x(){return this[0]}get y(){return this[1]}get z(){return this[2]}set x(e){this._target[0]=e,this.onChange()}set y(e){this._target[1]=e,this.onChange()}set z(e){this._target[2]=e,this.onChange()}set(e,t=e,n=e){return e.length?this.copy(e):(this._target[0]=e,this._target[1]=t,this._target[2]=n,this.onChange(),this)}copy(e){return this._target[0]=e[0],this._target[1]=e[1],this._target[2]=e[2],this.onChange(),this}reorder(e){return this._target.order=e,this.onChange(),this}fromRotationMatrix(e,t=this.order){return Be(this._target,e,t),this.onChange(),this}fromQuaternion(e,t=this.order,n){return Ve.fromQuaternion(e),this._target.fromRotationMatrix(Ve,t),n||this.onChange(),this}fromArray(e,t=0){return this._target[0]=e[t],this._target[1]=e[t+1],this._target[2]=e[t+2],this}toArray(e=[],t=0){return e[t]=this[0],e[t+1]=this[1],e[t+2]=this[2],e}},Ue=class{constructor(){this.parent=null,this.children=[],this.visible=!0,this.matrix=new ze,this.worldMatrix=new ze,this.matrixAutoUpdate=!0,this.worldMatrixNeedsUpdate=!1,this.position=new D,this.quaternion=new K,this.scale=new D(1),this.rotation=new He,this.up=new D(0,1,0),this.rotation._target.onChange=()=>this.quaternion.fromEuler(this.rotation,!0),this.quaternion._target.onChange=()=>this.rotation.fromQuaternion(this.quaternion,void 0,!0)}setParent(e,t=!0){this.parent&&e!==this.parent&&this.parent.removeChild(this,!1),this.parent=e,t&&e&&e.addChild(this,!1)}addChild(e,t=!0){~this.children.indexOf(e)||this.children.push(e),t&&e.setParent(this,!1)}removeChild(e,t=!0){~this.children.indexOf(e)&&this.children.splice(this.children.indexOf(e),1),t&&e.setParent(null,!1)}updateMatrixWorld(e){this.matrixAutoUpdate&&this.updateMatrix(),(this.worldMatrixNeedsUpdate||e)&&(this.parent===null?this.worldMatrix.copy(this.matrix):this.worldMatrix.multiply(this.parent.worldMatrix,this.matrix),this.worldMatrixNeedsUpdate=!1,e=!0);for(let t=0,n=this.children.length;t<n;t++)this.children[t].updateMatrixWorld(e)}updateMatrix(){this.matrix.compose(this.quaternion,this.position,this.scale),this.worldMatrixNeedsUpdate=!0}traverse(e){if(!e(this))for(let t=0,n=this.children.length;t<n;t++)this.children[t].traverse(e)}decompose(){this.matrix.decompose(this.quaternion._target,this.position,this.scale),this.rotation.fromQuaternion(this.quaternion)}lookAt(e,t=!1){t?this.matrix.lookAt(this.position,e,this.up):this.matrix.lookAt(e,this.position,this.up),this.matrix.getRotation(this.quaternion._target),this.rotation.fromQuaternion(this.quaternion)}};function We(e,t){return e[0]=t[0],e[1]=t[1],e[2]=t[2],e[3]=t[4],e[4]=t[5],e[5]=t[6],e[6]=t[8],e[7]=t[9],e[8]=t[10],e}function Ge(e,t){let n=t[0],r=t[1],i=t[2],a=t[3],o=n+n,s=r+r,c=i+i,l=n*o,u=r*o,d=r*s,f=i*o,p=i*s,m=i*c,h=a*o,g=a*s,_=a*c;return e[0]=1-d-m,e[3]=u-_,e[6]=f+g,e[1]=u+_,e[4]=1-l-m,e[7]=p-h,e[2]=f-g,e[5]=p+h,e[8]=1-l-d,e}function Ke(e,t){return e[0]=t[0],e[1]=t[1],e[2]=t[2],e[3]=t[3],e[4]=t[4],e[5]=t[5],e[6]=t[6],e[7]=t[7],e[8]=t[8],e}function qe(e,t,n,r,i,a,o,s,c,l){return e[0]=t,e[1]=n,e[2]=r,e[3]=i,e[4]=a,e[5]=o,e[6]=s,e[7]=c,e[8]=l,e}function Je(e){return e[0]=1,e[1]=0,e[2]=0,e[3]=0,e[4]=1,e[5]=0,e[6]=0,e[7]=0,e[8]=1,e}function Ye(e,t){let n=t[0],r=t[1],i=t[2],a=t[3],o=t[4],s=t[5],c=t[6],l=t[7],u=t[8],d=u*o-s*l,f=-u*a+s*c,p=l*a-o*c,m=n*d+r*f+i*p;return m?(m=1/m,e[0]=d*m,e[1]=(-u*r+i*l)*m,e[2]=(s*r-i*o)*m,e[3]=f*m,e[4]=(u*n-i*c)*m,e[5]=(-s*n+i*a)*m,e[6]=p*m,e[7]=(-l*n+r*c)*m,e[8]=(o*n-r*a)*m,e):null}function Xe(e,t,n){let r=t[0],i=t[1],a=t[2],o=t[3],s=t[4],c=t[5],l=t[6],u=t[7],d=t[8],f=n[0],p=n[1],m=n[2],h=n[3],g=n[4],_=n[5],v=n[6],y=n[7],b=n[8];return e[0]=f*r+p*o+m*l,e[1]=f*i+p*s+m*u,e[2]=f*a+p*c+m*d,e[3]=h*r+g*o+_*l,e[4]=h*i+g*s+_*u,e[5]=h*a+g*c+_*d,e[6]=v*r+y*o+b*l,e[7]=v*i+y*s+b*u,e[8]=v*a+y*c+b*d,e}function Ze(e,t,n){let r=t[0],i=t[1],a=t[2],o=t[3],s=t[4],c=t[5],l=t[6],u=t[7],d=t[8],f=n[0],p=n[1];return e[0]=r,e[1]=i,e[2]=a,e[3]=o,e[4]=s,e[5]=c,e[6]=f*r+p*o+l,e[7]=f*i+p*s+u,e[8]=f*a+p*c+d,e}function Qe(e,t,n){let r=t[0],i=t[1],a=t[2],o=t[3],s=t[4],c=t[5],l=t[6],u=t[7],d=t[8],f=Math.sin(n),p=Math.cos(n);return e[0]=p*r+f*o,e[1]=p*i+f*s,e[2]=p*a+f*c,e[3]=p*o-f*r,e[4]=p*s-f*i,e[5]=p*c-f*a,e[6]=l,e[7]=u,e[8]=d,e}function $e(e,t,n){let r=n[0],i=n[1];return e[0]=r*t[0],e[1]=r*t[1],e[2]=r*t[2],e[3]=i*t[3],e[4]=i*t[4],e[5]=i*t[5],e[6]=t[6],e[7]=t[7],e[8]=t[8],e}function et(e,t){let n=t[0],r=t[1],i=t[2],a=t[3],o=t[4],s=t[5],c=t[6],l=t[7],u=t[8],d=t[9],f=t[10],p=t[11],m=t[12],h=t[13],g=t[14],_=t[15],v=n*s-r*o,y=n*c-i*o,b=n*l-a*o,x=r*c-i*s,S=r*l-a*s,C=i*l-a*c,w=u*h-d*m,T=u*g-f*m,E=u*_-p*m,D=d*g-f*h,O=d*_-p*h,k=f*_-p*g,A=v*k-y*O+b*D+x*E-S*T+C*w;return A?(A=1/A,e[0]=(s*k-c*O+l*D)*A,e[1]=(c*E-o*k-l*T)*A,e[2]=(o*O-s*E+l*w)*A,e[3]=(i*O-r*k-a*D)*A,e[4]=(n*k-i*E+a*T)*A,e[5]=(r*E-n*O-a*w)*A,e[6]=(h*C-g*S+_*x)*A,e[7]=(g*b-m*C-_*y)*A,e[8]=(m*S-h*b+_*v)*A,e):null}var tt=class extends Array{constructor(e=1,t=0,n=0,r=0,i=1,a=0,o=0,s=0,c=1){return super(e,t,n,r,i,a,o,s,c),this}set(e,t,n,r,i,a,o,s,c){return e.length?this.copy(e):(qe(this,e,t,n,r,i,a,o,s,c),this)}translate(e,t=this){return Ze(this,t,e),this}rotate(e,t=this){return Qe(this,t,e),this}scale(e,t=this){return $e(this,t,e),this}multiply(e,t){return t?Xe(this,e,t):Xe(this,this,e),this}identity(){return Je(this),this}copy(e){return Ke(this,e),this}fromMatrix4(e){return We(this,e),this}fromQuaternion(e){return Ge(this,e),this}fromBasis(e,t,n){return this.set(e[0],e[1],e[2],t[0],t[1],t[2],n[0],n[1],n[2]),this}inverse(e=this){return Ye(this,e),this}getNormalMatrix(e){return et(this,e),this}},nt=0,rt=class extends Ue{constructor(e,{geometry:t,program:n,mode:r=e.TRIANGLES,frustumCulled:i=!0,renderOrder:a=0}={}){super(),e.canvas||console.error(`gl not passed as first argument to Mesh`),this.gl=e,this.id=nt++,this.geometry=t,this.program=n,this.mode=r,this.frustumCulled=i,this.renderOrder=a,this.modelViewMatrix=new ze,this.normalMatrix=new tt,this.beforeRenderCallbacks=[],this.afterRenderCallbacks=[]}onBeforeRender(e){return this.beforeRenderCallbacks.push(e),this}onAfterRender(e){return this.afterRenderCallbacks.push(e),this}draw({camera:e}={}){e&&(this.program.uniforms.modelMatrix||Object.assign(this.program.uniforms,{modelMatrix:{value:null},viewMatrix:{value:null},modelViewMatrix:{value:null},normalMatrix:{value:null},projectionMatrix:{value:null},cameraPosition:{value:null}}),this.program.uniforms.projectionMatrix.value=e.projectionMatrix,this.program.uniforms.cameraPosition.value=e.worldPosition,this.program.uniforms.viewMatrix.value=e.viewMatrix,this.modelViewMatrix.multiply(e.viewMatrix,this.worldMatrix),this.normalMatrix.getNormalMatrix(this.modelViewMatrix),this.program.uniforms.modelMatrix.value=this.worldMatrix,this.program.uniforms.modelViewMatrix.value=this.modelViewMatrix,this.program.uniforms.normalMatrix.value=this.normalMatrix),this.beforeRenderCallbacks.forEach(t=>t&&t({mesh:this,camera:e}));let t=this.program.cullFace&&this.worldMatrix.determinant()<0;this.program.use({flipFaces:t}),this.geometry.draw({mode:this.mode,program:this.program}),this.afterRenderCallbacks.forEach(t=>t&&t({mesh:this,camera:e}))}},it=new Uint8Array(4);function at(e){return!(e&e-1)}var ot=1,st=class{constructor(e,{image:t,target:n=e.TEXTURE_2D,type:r=e.UNSIGNED_BYTE,format:i=e.RGBA,internalFormat:a=i,wrapS:o=e.CLAMP_TO_EDGE,wrapT:s=e.CLAMP_TO_EDGE,wrapR:c=e.CLAMP_TO_EDGE,generateMipmaps:l=n===(e.TEXTURE_2D||e.TEXTURE_CUBE_MAP),minFilter:u=l?e.NEAREST_MIPMAP_LINEAR:e.LINEAR,magFilter:d=e.LINEAR,premultiplyAlpha:f=!1,unpackAlignment:p=4,flipY:m=n==(e.TEXTURE_2D||e.TEXTURE_3D),anisotropy:h=0,level:g=0,width:_,height:v=_,length:y=1}={}){this.gl=e,this.id=ot++,this.image=t,this.target=n,this.type=r,this.format=i,this.internalFormat=a,this.minFilter=u,this.magFilter=d,this.wrapS=o,this.wrapT=s,this.wrapR=c,this.generateMipmaps=l,this.premultiplyAlpha=f,this.unpackAlignment=p,this.flipY=m,this.anisotropy=Math.min(h,this.gl.renderer.parameters.maxAnisotropy),this.level=g,this.width=_,this.height=v,this.length=y,this.texture=this.gl.createTexture(),this.store={image:null},this.glState=this.gl.renderer.state,this.state={},this.state.minFilter=this.gl.NEAREST_MIPMAP_LINEAR,this.state.magFilter=this.gl.LINEAR,this.state.wrapS=this.gl.REPEAT,this.state.wrapT=this.gl.REPEAT,this.state.anisotropy=0}bind(){this.glState.textureUnits[this.glState.activeTextureUnit]!==this.id&&(this.gl.bindTexture(this.target,this.texture),this.glState.textureUnits[this.glState.activeTextureUnit]=this.id)}update(e=0){let t=!(this.image===this.store.image&&!this.needsUpdate);if((t||this.glState.textureUnits[e]!==this.id)&&(this.gl.renderer.activeTexture(e),this.bind()),t){if(this.needsUpdate=!1,this.flipY!==this.glState.flipY&&(this.gl.pixelStorei(this.gl.UNPACK_FLIP_Y_WEBGL,this.flipY),this.glState.flipY=this.flipY),this.premultiplyAlpha!==this.glState.premultiplyAlpha&&(this.gl.pixelStorei(this.gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,this.premultiplyAlpha),this.glState.premultiplyAlpha=this.premultiplyAlpha),this.unpackAlignment!==this.glState.unpackAlignment&&(this.gl.pixelStorei(this.gl.UNPACK_ALIGNMENT,this.unpackAlignment),this.glState.unpackAlignment=this.unpackAlignment),this.minFilter!==this.state.minFilter&&(this.gl.texParameteri(this.target,this.gl.TEXTURE_MIN_FILTER,this.minFilter),this.state.minFilter=this.minFilter),this.magFilter!==this.state.magFilter&&(this.gl.texParameteri(this.target,this.gl.TEXTURE_MAG_FILTER,this.magFilter),this.state.magFilter=this.magFilter),this.wrapS!==this.state.wrapS&&(this.gl.texParameteri(this.target,this.gl.TEXTURE_WRAP_S,this.wrapS),this.state.wrapS=this.wrapS),this.wrapT!==this.state.wrapT&&(this.gl.texParameteri(this.target,this.gl.TEXTURE_WRAP_T,this.wrapT),this.state.wrapT=this.wrapT),this.wrapR!==this.state.wrapR&&(this.gl.texParameteri(this.target,this.gl.TEXTURE_WRAP_R,this.wrapR),this.state.wrapR=this.wrapR),this.anisotropy&&this.anisotropy!==this.state.anisotropy&&(this.gl.texParameterf(this.target,this.gl.renderer.getExtension(`EXT_texture_filter_anisotropic`).TEXTURE_MAX_ANISOTROPY_EXT,this.anisotropy),this.state.anisotropy=this.anisotropy),this.image){if(this.image.width&&(this.width=this.image.width,this.height=this.image.height),this.target===this.gl.TEXTURE_CUBE_MAP)for(let e=0;e<6;e++)this.gl.texImage2D(this.gl.TEXTURE_CUBE_MAP_POSITIVE_X+e,this.level,this.internalFormat,this.format,this.type,this.image[e]);else if(ArrayBuffer.isView(this.image))this.target===this.gl.TEXTURE_2D?this.gl.texImage2D(this.target,this.level,this.internalFormat,this.width,this.height,0,this.format,this.type,this.image):(this.target===this.gl.TEXTURE_2D_ARRAY||this.target===this.gl.TEXTURE_3D)&&this.gl.texImage3D(this.target,this.level,this.internalFormat,this.width,this.height,this.length,0,this.format,this.type,this.image);else if(this.image.isCompressedTexture)for(let e=0;e<this.image.length;e++)this.gl.compressedTexImage2D(this.target,e,this.internalFormat,this.image[e].width,this.image[e].height,0,this.image[e].data);else this.target===this.gl.TEXTURE_2D?this.gl.texImage2D(this.target,this.level,this.internalFormat,this.format,this.type,this.image):this.gl.texImage3D(this.target,this.level,this.internalFormat,this.width,this.height,this.length,0,this.format,this.type,this.image);this.generateMipmaps&&(!this.gl.renderer.isWebgl2&&(!at(this.image.width)||!at(this.image.height))?(this.generateMipmaps=!1,this.wrapS=this.wrapT=this.gl.CLAMP_TO_EDGE,this.minFilter=this.gl.LINEAR):this.gl.generateMipmap(this.target)),this.onUpdate&&this.onUpdate()}else if(this.target===this.gl.TEXTURE_CUBE_MAP)for(let e=0;e<6;e++)this.gl.texImage2D(this.gl.TEXTURE_CUBE_MAP_POSITIVE_X+e,0,this.gl.RGBA,1,1,0,this.gl.RGBA,this.gl.UNSIGNED_BYTE,it);else this.width?this.target===this.gl.TEXTURE_2D?this.gl.texImage2D(this.target,this.level,this.internalFormat,this.width,this.height,0,this.format,this.type,null):this.gl.texImage3D(this.target,this.level,this.internalFormat,this.width,this.height,this.length,0,this.format,this.type,null):this.gl.texImage2D(this.target,0,this.gl.RGBA,1,1,0,this.gl.RGBA,this.gl.UNSIGNED_BYTE,it);this.store.image=this.image}}},ct=class{constructor(e,{width:t=e.canvas.width,height:n=e.canvas.height,target:r=e.FRAMEBUFFER,color:i=1,depth:a=!0,stencil:o=!1,depthTexture:s=!1,wrapS:c=e.CLAMP_TO_EDGE,wrapT:l=e.CLAMP_TO_EDGE,wrapR:u=e.CLAMP_TO_EDGE,minFilter:d=e.LINEAR,magFilter:f=d,type:p=e.UNSIGNED_BYTE,format:m=e.RGBA,internalFormat:h=m,unpackAlignment:g,premultiplyAlpha:_}={}){this.gl=e,this.width=t,this.height=n,this.depth=a,this.stencil=o,this.buffer=this.gl.createFramebuffer(),this.target=r,this.gl.renderer.bindFramebuffer(this),this.textures=[];let v=[];for(let r=0;r<i;r++)this.textures.push(new st(e,{width:t,height:n,wrapS:c,wrapT:l,wrapR:u,minFilter:d,magFilter:f,type:p,format:m,internalFormat:h,unpackAlignment:g,premultiplyAlpha:_,flipY:!1,generateMipmaps:!1})),this.textures[r].update(),this.gl.framebufferTexture2D(this.target,this.gl.COLOR_ATTACHMENT0+r,this.gl.TEXTURE_2D,this.textures[r].texture,0),v.push(this.gl.COLOR_ATTACHMENT0+r);v.length>1&&this.gl.renderer.drawBuffers(v),this.texture=this.textures[0],s&&(this.gl.renderer.isWebgl2||this.gl.renderer.getExtension(`WEBGL_depth_texture`))?(this.depthTexture=new st(e,{width:t,height:n,minFilter:this.gl.NEAREST,magFilter:this.gl.NEAREST,format:this.stencil?this.gl.DEPTH_STENCIL:this.gl.DEPTH_COMPONENT,internalFormat:e.renderer.isWebgl2?this.stencil?this.gl.DEPTH24_STENCIL8:this.gl.DEPTH_COMPONENT16:this.gl.DEPTH_COMPONENT,type:this.stencil?this.gl.UNSIGNED_INT_24_8:this.gl.UNSIGNED_INT}),this.depthTexture.update(),this.gl.framebufferTexture2D(this.target,this.stencil?this.gl.DEPTH_STENCIL_ATTACHMENT:this.gl.DEPTH_ATTACHMENT,this.gl.TEXTURE_2D,this.depthTexture.texture,0)):(a&&!o&&(this.depthBuffer=this.gl.createRenderbuffer(),this.gl.bindRenderbuffer(this.gl.RENDERBUFFER,this.depthBuffer),this.gl.renderbufferStorage(this.gl.RENDERBUFFER,this.gl.DEPTH_COMPONENT16,t,n),this.gl.framebufferRenderbuffer(this.target,this.gl.DEPTH_ATTACHMENT,this.gl.RENDERBUFFER,this.depthBuffer)),o&&!a&&(this.stencilBuffer=this.gl.createRenderbuffer(),this.gl.bindRenderbuffer(this.gl.RENDERBUFFER,this.stencilBuffer),this.gl.renderbufferStorage(this.gl.RENDERBUFFER,this.gl.STENCIL_INDEX8,t,n),this.gl.framebufferRenderbuffer(this.target,this.gl.STENCIL_ATTACHMENT,this.gl.RENDERBUFFER,this.stencilBuffer)),a&&o&&(this.depthStencilBuffer=this.gl.createRenderbuffer(),this.gl.bindRenderbuffer(this.gl.RENDERBUFFER,this.depthStencilBuffer),this.gl.renderbufferStorage(this.gl.RENDERBUFFER,this.gl.DEPTH_STENCIL,t,n),this.gl.framebufferRenderbuffer(this.target,this.gl.DEPTH_STENCIL_ATTACHMENT,this.gl.RENDERBUFFER,this.depthStencilBuffer))),this.gl.renderer.bindFramebuffer({target:this.target})}setSize(e,t){if(this.width!==e||this.height!==t){this.width=e,this.height=t,this.gl.renderer.bindFramebuffer(this);for(let n=0;n<this.textures.length;n++)this.textures[n].width=e,this.textures[n].height=t,this.textures[n].needsUpdate=!0,this.textures[n].update(),this.gl.framebufferTexture2D(this.target,this.gl.COLOR_ATTACHMENT0+n,this.gl.TEXTURE_2D,this.textures[n].texture,0);this.depthTexture?(this.depthTexture.width=e,this.depthTexture.height=t,this.depthTexture.needsUpdate=!0,this.depthTexture.update(),this.gl.framebufferTexture2D(this.target,this.gl.DEPTH_ATTACHMENT,this.gl.TEXTURE_2D,this.depthTexture.texture,0)):(this.depthBuffer&&(this.gl.bindRenderbuffer(this.gl.RENDERBUFFER,this.depthBuffer),this.gl.renderbufferStorage(this.gl.RENDERBUFFER,this.gl.DEPTH_COMPONENT16,e,t)),this.stencilBuffer&&(this.gl.bindRenderbuffer(this.gl.RENDERBUFFER,this.stencilBuffer),this.gl.renderbufferStorage(this.gl.RENDERBUFFER,this.gl.STENCIL_INDEX8,e,t)),this.depthStencilBuffer&&(this.gl.bindRenderbuffer(this.gl.RENDERBUFFER,this.depthStencilBuffer),this.gl.renderbufferStorage(this.gl.RENDERBUFFER,this.gl.DEPTH_STENCIL,e,t))),this.gl.renderer.bindFramebuffer({target:this.target})}}},lt=class extends M{constructor(e,{attributes:t={}}={}){Object.assign(t,{position:{size:2,data:new Float32Array([-1,-1,3,-1,-1,3])},uv:{size:2,data:new Float32Array([0,0,2,0,0,2])}}),super(e,t)}},ut=e(t(),1),dt=n(),ft={plasma:{color:`#F25BD0`,strands:6,crackle:.85,flares:.65,glow:.9,sparks:.6,particleCount:15e3,fill:.5,motion:`rise`,particleShape:`square`,depth:.6,sway:.5,twinkle:.5,haze:.7,dustSpeed:1},aurora:{color:`#5CFFC8`,strands:5,crackle:.6,flares:.5,glow:.8,sparks:.45,particleCount:15e3,fill:.5,motion:`rise`,particleShape:`square`,depth:.6,sway:.5,twinkle:.5,haze:.7,dustSpeed:1},nebula:{color:`#9478FF`,strands:6,crackle:1,flares:.5,glow:.9,sparks:.6,particleCount:18e3,fill:.45,motion:`rise`,particleShape:`square`,depth:.5,sway:.4,twinkle:.6,haze:.8,dustSpeed:1.2},ember:{color:`#FF8A2A`,strands:5,crackle:.9,flares:.8,glow:1,sparks:.8,particleCount:12e3,fill:.35,motion:`rise`,particleShape:`round`,depth:.7,sway:.3,twinkle:.7,haze:.9,dustSpeed:1.6},frost:{color:`#BFE6FF`,strands:3,crackle:.3,flares:.3,glow:.6,sparks:.2,particleCount:16e3,fill:.6,motion:`fall`,particleShape:`round`,depth:.8,sway:.4,twinkle:.4,haze:.5,dustSpeed:.7},solar:{color:`#FFD36E`,strands:6,crackle:.7,flares:1,glow:1.1,sparks:.5,particleCount:15e3,fill:.55,motion:`orbit`,particleShape:`square`,depth:.6,sway:.7,twinkle:.5,haze:.8,dustSpeed:1},eclipse:{color:`#FFFFFF`,strands:4,crackle:.5,flares:.4,glow:.7,sparks:.35,particleCount:14e3,fill:.5,motion:`drift`,particleShape:`square`,depth:.7,sway:.5,twinkle:.5,haze:.5,dustSpeed:.8},abyss:{color:`#3F7BFF`,strands:5,crackle:.55,flares:.6,glow:.9,sparks:.4,particleCount:2e4,fill:.8,motion:`orbit`,particleShape:`round`,depth:.8,sway:.8,twinkle:.5,haze:.6,dustSpeed:.9}},pt={rise:0,fall:1,drift:2,orbit:3},mt={square:0,round:1},ht=8,gt=4,_t=4e4,X=256,vt=45e5,yt=2.2,bt=7,xt=[1,1,1],St=[0,0,0],Z=(e,t,n)=>Math.min(Math.max(e,t),n),Q=(e,t,n)=>{let r=Z((n-e)/(t-e),0,1);return r*r*(3-2*r)},Ct=e=>1-(1-e)**3,wt=(e,t,n)=>e.map((e,r)=>e+(t[r]-e)*n),Tt=e=>e-Math.PI*2*Math.floor((e+Math.PI)/(Math.PI*2)),Et=(e,t)=>{try{let n=document.createElement(`canvas`).getContext(`2d`);if(!n)return t;n.fillStyle=`#000000`,n.fillStyle=e;let r=n.fillStyle;if(r.startsWith(`#`)){let e=parseInt(r.slice(1),16);return[(e>>16&255)/255,(e>>8&255)/255,(e&255)/255]}let i=r.match(/[\d.]+/g);return!i||i.length<3?t:[Number(i[0])/255,Number(i[1])/255,Number(i[2])/255]}catch{return t}},Dt=e=>e<=.04045?e/12.92:((e+.055)/1.055)**2.4,Ot=e=>e<=.0031308?e*12.92:1.055*e**(1/2.4)-.055,kt=([e,t,n])=>{let[r,i,a]=[Dt(e),Dt(t),Dt(n)],o=Math.cbrt(.4122214708*r+.5363325363*i+.0514459929*a),s=Math.cbrt(.2119034982*r+.6806995451*i+.1073969566*a),c=Math.cbrt(.0883024619*r+.2817188376*i+.6299787005*a);return[.2104542553*o+.793617785*s-.0040720468*c,1.9779984951*o-2.428592205*s+.4505937099*c,.0259040371*o+.7827717662*s-.808675766*c]},At=([e,t,n])=>{let r=(e+.3963377774*t+.2158037573*n)**3,i=(e-.1055613458*t-.0638541728*n)**3,a=(e-.0894841775*t-1.291485548*n)**3;return[4.0767416621*r-3.3077115913*i+.2309699292*a,-1.2684380046*r+2.6097574011*i-.3413193965*a,-.0041960863*r-.7034186147*i+1.707614701*a].map(e=>Z(Ot(Z(e,0,1)),0,1))},jt=(e,t,n)=>At(wt(kt(e),kt(t),n)),Mt=(e,t,n,r)=>{let[i,a,o]=kt(e),s=Math.hypot(a,o)*r,c=Math.atan2(o,a)+t*Math.PI/180;return At([Z(i+n,0,1),s*Math.cos(c),s*Math.sin(c)])},$=(e,t,n,r)=>{let[,i,a]=kt(e),o=Math.max(Math.hypot(i,a)*r,.02),s=Math.atan2(a,i)+t*Math.PI/180;return At([Z(n,0,1),o*Math.cos(s),o*Math.sin(s)])},Nt=(e,t)=>{if(t){let t=$(e,0,Math.min(kt(e)[0],.62),1.15);return{rim:t,rimHot:t,rimMid:t,rimDeep:$(e,0,.72,.8),spark:$(e,0,.6,1.2),sparkGlow:$(e,0,.78,.8),haze:$(e,0,.8,.6),edge:$(e,0,.72,.8),tones:[$(e,0,.56,1.1),$(e,16,.6,1.05),$(e,-16,.5,1.1),$(e,0,.66,.9),$(e,0,.74,.7)]}}return{rim:e,rimHot:wt(e,xt,.72),rimMid:wt(e,St,.15),rimDeep:wt(e,St,.45),spark:wt(e,xt,.45),sparkGlow:Mt(e,0,-.15,1),haze:wt(e,St,.6),edge:Mt(e,0,-.3,.9),tones:[Mt(e,0,-.06,1),Mt(e,16,-.02,1),Mt(e,-16,-.12,1.05),Mt(jt(e,xt,.25),0,.04,1),jt(e,xt,.7)]}},Pt=e=>{let t=e>>>0;return()=>{t=t+1831565813>>>0;let e=t;return e=Math.imul(e^e>>>15,e|1),e^=e+Math.imul(e^e>>>7,e|61),((e^e>>>14)>>>0)/4294967296}},Ft=()=>{let e=Pt(99),t=[[6,12,.6,1.6],[18,34,1.5,3.5],[40,70,3,7],[80,130,6,12]],n={harmonics:[],rates:[],phases:[],flareHarmonics:[],flareRates:[],flarePhases:[]};for(let r=0;r<ht;r++){t.forEach(([t,r,i,a])=>{n.harmonics.push(Math.round(t+e()*(r-t))),n.rates.push((i+e()*(a-i))*(e()<.5?-1:1)),n.phases.push(e()*Math.PI*2)});for(let t=0;t<3;t++)n.flareHarmonics.push(4+Math.floor(e()*6)),n.flareRates.push((.4+e()*.8)*(e()<.5?-1:1)),n.flarePhases.push(e()*Math.PI*2);let i=r===0;n.flareHarmonics.push(i?.75:.95+e()*.3),n.flareRates.push(i?1.15:.8+e()*.2),n.flarePhases.push(i?1:.7+e()*.25)}return n},It=e=>{let t=Pt(1337),n=Math.max(1,Math.ceil(e/X)),r=new Float32Array(X*n*4),i=new Float32Array(X*n*4),a=0,o=0;for(;a<e&&o<e*80;){o++;let e,n,s;if(t()<.28){let r=t()*Math.PI*2,i=.87+Math.sqrt(t())*.105;if(e=Math.cos(r)*i,n=Math.sin(r)*i,t()>Q(-.6,.3,-n))continue;let a=t();s=a<.5?3:a<.8?2:1}else{e=t()*2-1,n=t()*2-1;let r=Math.hypot(e,n);if(r>.975)continue;let i=Q(-.25,.85,-n)**1.3,a=Q(.66,.96,r)*Q(-.7,.3,-n),o=Math.max(i,a*.9);if(t()>.012+.988*o)continue;if(o<.12)s=4;else{let e=t();s=e<.32?0:e<.52?1:e<.8?2:3}}let c=Math.sqrt(Math.max(0,.95-e*e-n*n));r[a*4]=e,r[a*4+1]=n,r[a*4+2]=(t()*2-1)*c,r[a*4+3]=s,i[a*4]=s===4?1.8:t()<.22?2.1:1.3,i[a*4+1]=t(),i[a*4+2]=2.5+t()*3.5,i[a*4+3]=.16+t()*.26,a++}return{home:r,seed:i,count:a,rows:n}},Lt=`#version 300 es
in vec2 position;
in vec2 uv;
out vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position, 0.0, 1.0);
}
`,Rt=`
uint scramble(uint v) {
  v = v * 747796405u + 2891336453u;
  uint w = ((v >> ((v >> 28u) + 4u)) ^ v) * 277803737u;
  return (w >> 22u) ^ w;
}

float random(uint v) {
  return float(scramble(v)) * (1.0 / 4294967295.0);
}
`,zt=`
uniform float uDustTime;
uniform vec2 uTurn;
uniform float uMotion;
uniform float uFill;

vec3 settle(vec3 p, out float spread) {
  float bend = exp2((0.5 - uFill) * 1.8);
  float h = clamp((p.y + 1.0) * 0.5, 0.0, 1.0);
  float y = 2.0 * pow(h, bend) - 1.0;
  float from = sqrt(max(1.0 - p.y * p.y, 1e-4));
  float to = sqrt(max(1.0 - y * y, 0.0));
  spread = clamp(bend * pow(max(h, 1e-3), bend - 1.0) * to / from, 0.25, 1.0);
  return vec3(p.xz * (to / from), y).xzy;
}

vec3 drift(vec4 home, vec4 seed, uint id, out float life, out float spread) {
  vec3 p = settle(home.xyz, spread);
  float t = uDustTime;
  float u = fract(t / seed.z + seed.y);
  life = sin(3.14159265 * u);
  float travel = seed.w;
  if (uMotion < 0.5) {
    p.y += travel * (u - 0.5);
  } else if (uMotion < 1.5) {
    p.y -= travel * (u - 0.5);
  } else if (uMotion < 2.5) {
    p += 0.045 * vec3(
      sin(t * 0.37 + seed.y * 17.0) + 0.5 * sin(t * 0.83 + seed.z * 5.0),
      sin(t * 0.29 + seed.z * 11.0) + 0.5 * sin(t * 0.61 + seed.w * 7.0),
      sin(t * 0.33 + seed.w * 23.0)
    );
  } else {
    float loop = t * (0.6 + 0.9 * random(id * 7u + 3u)) * (random(id * 7u + 10u) < 0.5 ? -1.0 : 1.0) + seed.y * 6.2831853;
    p.xy += (0.025 + 0.05 * random(id * 7u + 16u)) * vec2(cos(loop), sin(loop));
  }
  float wobble = 0.002 + 0.006 * random(id * 7u + 1u);
  float w1 = 0.8 + 2.4 * random(id * 7u + 2u);
  float w2 = 0.8 + 2.4 * random(id * 7u + 4u);
  p += wobble * vec3(sin(t * w1 + seed.y * 40.0), cos(t * w2 + seed.z * 30.0), sin(t * (w1 + w2) * 0.5 + seed.w * 20.0));
  float cy = cos(uTurn.x);
  float sy = sin(uTurn.x);
  p.xz = mat2(cy, -sy, sy, cy) * p.xz;
  float cx = cos(uTurn.y);
  float sx = sin(uTurn.y);
  p.yz = mat2(cx, -sx, sx, cx) * p.yz;
  return p;
}
`,Bt=`#version 300 es
precision highp float;

uniform vec2 uCenter;
uniform float uRadius;
uniform float uDpr;
uniform float uLine;
uniform float uTime;
uniform float uFrame;
uniform float uBins;
uniform float uStrands;
uniform float uCrackle;
uniform float uFlares;
uniform float uGlow;
uniform float uHaze;
uniform float uFill;
uniform float uPresence;
uniform float uUnfold;
uniform float uBloom;
uniform float uInside;
uniform float uEncode;
uniform vec3 uRim;
uniform vec3 uRimHot;
uniform vec3 uRimMid;
uniform vec3 uRimDeep;
uniform vec3 uSpark;
uniform vec3 uSparkGlow;
uniform vec3 uHazeColor;
uniform vec3 uEdgeColor;
uniform vec4 uHeat;
uniform vec4 uHarmonics[8];
uniform vec4 uRates[8];
uniform vec4 uPhases[8];
uniform vec4 uFlareHarmonics[8];
uniform vec4 uFlareRates[8];
uniform vec4 uFlarePhases[8];
uniform vec4 uArcs[4];

out vec4 fragColor;
${Rt}
const float PI = 3.14159265;
const float TAU = 6.28318531;
const vec4 AMPS = vec4(0.35, 0.3, 0.22, 0.13);

float bell(float d, float w) {
  float x = d / w;
  return exp(-x * x);
}

float segment(vec2 p, vec2 a, vec2 b) {
  vec2 pa = p - a;
  vec2 ba = b - a;
  float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-5), 0.0, 1.0);
  return length(pa - ba * h);
}

float pool(vec2 q) {
  float t = length(q - vec2(0.0, mix(-1.0, -0.66, uFill))) / mix(0.8, 1.35, uFill);
  return t < 0.6 ? mix(0.5, 0.22, t / 0.6) : mix(0.22, 0.0, clamp((t - 0.6) / 0.4, 0.0, 1.0));
}

void main() {
  vec2 p = gl_FragCoord.xy / uDpr - uCenter;
  float r = length(p);
  float R = uRadius;
  float theta = atan(p.y, p.x);
  float lift = p.y / max(r, 1e-3);
  float topDim = 1.0 - 0.35 * pow(max(lift, 0.0), 1.5);
  vec3 col = vec3(0.0);
  float hot = 0.0;
  uint frame = uint(uFrame);

  if (r < R) {
    vec2 q = p / R;
    float chord = sqrt(max(1.0 - dot(q, q), 0.0));
    float haze = pool(q) * (0.55 + 0.45 * chord);
    col += uHazeColor * haze * uHaze * uInside;
    float e = length(q - vec2(0.0, 0.2)) / 1.2;
    float edge = 0.5 * pow(smoothstep(0.62, 1.0, e), 1.4);
    col += uEdgeColor * edge * uInside * (0.5 + 0.5 * uHaze);
  }

  float dr = r - R;
  float halo = 1.0 - smoothstep(R * 0.05, R * 0.105, abs(dr - R * 0.0213));
  col += uRimDeep * 0.18 * halo * topDim * uGlow * uBloom;
  col += uRim * 0.12 * bell(dr + R * 0.0383, R * 0.032) * uGlow * uBloom;
  col += uRim * 0.32 * bell(dr, max(R * 0.0117, uLine)) * uPresence * uUnfold;

  float delta = mod(theta - uHeat.x + PI, TAU) - PI;
  float heat = uHeat.z * uHeat.y * exp(-delta * delta / 0.3);
  float crackle = uCrackle + heat * 0.9;
  float amp = R * 0.016 * (0.3 + 1.4 * crackle) * uUnfold;
  float jitterAmp = R * 0.0048 * (0.3 + 1.4 * uCrackle) * uUnfold * (1.0 + heat * 0.3);
  float flareAmp = R * 0.064 * (0.4 + 1.2 * crackle) * uFlares * 1.6 * uUnfold;

  if (abs(dr) < amp * 2.0 + flareAmp + R * 0.3) {
    float step = TAU / uBins;
    float binPos = (theta + PI) / step;
    float bin0 = floor(binPos);
    float binF = binPos - bin0;
    float th0 = bin0 * step - PI;
    float th1 = th0 + step;
    uint b0 = uint(mod(bin0, uBins));
    uint b1 = uint(mod(bin0 + 1.0, uBins));
    float gain = min(1.0, 2.4 / max(uStrands, 1.0));
    for (int k = 0; k < 8; k++) {
      if (float(k) >= uStrands) break;
      vec4 m = uHarmonics[k];
      vec4 lead = uRates[k] * uTime + uPhases[k];
      float wave0 = dot(AMPS, sin(m * th0 + lead));
      float wave1 = dot(AMPS, sin(m * th1 + lead));
      uint salt = uint(k) * 1013u + frame * 7919u;
      vec4 shape = uFlareHarmonics[k];
      vec4 look = uFlareRates[k];
      vec4 tone = uFlarePhases[k];
      float a = amp * shape.w;
      float off0 = a * wave0 + jitterAmp * (random(b0 + salt) - 0.5);
      float off1 = a * wave1 + jitterAmp * (random(b1 + salt) - 0.5);
      float rc = R + mix(off0, off1, binF);
      float grade = (off1 - off0) / (step * max(r, 1.0));
      float d = abs(r - rc) * inversesqrt(1.0 + grade * grade);
      float swell = 0.8 + 0.4 * (0.5 + 0.5 * sin(3.0 * theta + uTime * 0.7 + tone.x * 1.7));
      float width = uLine * look.w * swell * (1.0 + heat * 0.25);
      float core = exp(-d * d / (width * width));
      float sheath = exp(-d * d / (width * width * 3.0));
      float bright = tone.w * (1.0 + heat * 0.45) * uPresence;
      col += (uRimHot * core * 0.8 + uRim * sheath * 0.32) * bright;
      hot += core * bright;
      vec3 fargs = shape.xyz * theta + look.xyz * uTime + tone.xyz;
      float flare = max(0.0, (sin(fargs.x) + sin(fargs.y) + sin(fargs.z)) / 3.0);
      flare = (flare * flare + heat * 0.35) * flareAmp;
      float dw = abs(r - rc - flare);
      float dm = abs(r - rc - flare * 0.6);
      float dn = abs(r - rc - flare * 0.25);
      vec3 glow = uRimDeep * (0.07 * bell(dw, R * 0.09) + 0.16 * bell(dw, R * 0.05));
      glow += uRimMid * 0.28 * bell(dm, R * 0.027) + uRim * 0.38 * bell(dn, R * 0.013);
      col += glow * gain * topDim * uGlow * uBloom * (1.0 + heat * 1.4);
    }
  }

  for (int i = 0; i < 4; i++) {
    vec4 arc = uArcs[i];
    if (arc.w <= 0.002) continue;
    float mid = arc.x + arc.y * 0.5;
    vec2 center = R * 0.93 * vec2(cos(mid), sin(mid));
    if (distance(p, center) > R * (abs(arc.y) * 0.6 + 0.1) + 12.0) continue;
    float ar = R * 0.955;
    vec2 a0 = ar * vec2(cos(arc.x), sin(arc.x));
    vec2 a2 = ar * vec2(cos(arc.x + arc.y), sin(arc.x + arc.y));
    vec2 a1 = R * (0.955 - arc.z) * vec2(cos(mid), sin(mid));
    float dmin = 1e5;
    float along = 0.0;
    vec2 prev = a0;
    for (int s = 1; s <= 10; s++) {
      float u = float(s) / 10.0;
      vec2 b = mix(mix(a0, a1, u), mix(a1, a2, u), u);
      vec2 pa = p - prev;
      vec2 ba = b - prev;
      float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-5), 0.0, 1.0);
      float dist = length(pa - ba * h);
      if (dist < dmin) {
        dmin = dist;
        along = (float(s) - 1.0 + h) / 10.0;
      }
      prev = b;
    }
    float taper = sqrt(max(sin(PI * along), 0.0));
    float arcWidth = uLine * (0.55 + 0.6 * taper);
    float arcCore = exp(-dmin * dmin / (arcWidth * arcWidth));
    float arcGlow = exp(-dmin * dmin / (arcWidth * arcWidth * 12.0));
    col += (uSpark * 0.95 * arcCore + uSparkGlow * 0.4 * arcGlow) * arc.w * taper;
    hot += arcCore * arc.w * taper * 0.6;
  }

  fragColor = vec4(col, hot) * uEncode;
}
`,Vt=`#version 300 es
precision highp float;

in float aIndex;

uniform sampler2D tHome;
uniform sampler2D tSeed;
uniform sampler2D tOffset;
uniform float uStirred;
uniform vec2 uCenter;
uniform vec2 uViewport;
uniform float uRadius;
uniform float uDpr;
uniform float uDepth;
uniform float uTwinkle;
uniform float uPointScale;
uniform float uReveal;
uniform float uEncode;
uniform vec3 uTones[5];
uniform vec3 uRimTone;

out vec3 vColor;
out float vSize;
${Rt}
${zt}
void main() {
  ivec2 cell = ivec2(int(mod(aIndex, ${X}.0)), int(floor(aIndex / ${X}.0)));
  uint id = uint(aIndex);
  vec4 home = texelFetch(tHome, cell, 0);
  vec4 seed = texelFetch(tSeed, cell, 0);
  float life;
  float spread;
  vec3 p = drift(home, seed, id, life, spread);
  if (uStirred > 0.5) p += texelFetch(tOffset, cell, 0).xyz;
  float len = length(p);
  float inside = 1.0 - smoothstep(0.955, 0.985, length(p.xy));
  if (len > 0.975) p *= 0.975 / len;

  float front = p.z * 0.5 + 0.5;
  float depthSize = mix(1.0, 0.7 + 0.6 * front, uDepth);
  float depthLight = mix(1.0, 0.35 + 0.8 * front, uDepth);
  float blink = sin(uDustTime * (2.0 + 6.0 * random(id * 7u + 5u)) + random(id * 7u + 6u) * 6.2831853);
  float twinkle = mix(1.0, smoothstep(-0.9, -0.6, blink), uTwinkle);
  float fade = smoothstep(0.04, 0.12, life);
  float order = (home.y + 1.0) * 0.5 * 0.55 + random(id * 7u + 8u) * 0.25;
  float reveal = smoothstep(order, order + 0.2, uReveal * 1.0);
  float alpha = random(id * 7u + 9u) < 0.5 || home.w > 3.5 ? 1.0 : 0.6;

  float size = seed.x * uPointScale * (0.35 + 0.95 * life) * depthSize * mix(0.5, 1.0, reveal);
  vec2 screen = uCenter + p.xy * uRadius;
  gl_Position = vec4(screen / uViewport * 2.0 - 1.0, 0.0, 1.0);
  float px = size * uDpr;
  gl_PointSize = px + 2.0;
  vSize = px;

  int tone = int(home.w + 0.5);
  float rimLit = smoothstep(0.8, 0.97, length(p.xy));
  vec3 color = uTones[tone] + uRimTone * rimLit * rimLit * 0.12;
  vColor = color * alpha * fade * twinkle * depthLight * reveal * inside * sqrt(spread) * uEncode;
}
`,Ht=`#version 300 es
precision highp float;

uniform float uShape;

in vec3 vColor;
in float vSize;

out vec4 fragColor;

void main() {
  vec2 q = (gl_PointCoord - 0.5) * (vSize + 2.0);
  float half_ = max(vSize * 0.5, 0.5);
  float cover;
  if (uShape < 0.5) {
    vec2 c = clamp(half_ - abs(q) + 0.5, 0.0, 1.0);
    cover = c.x * c.y;
  } else {
    cover = clamp(half_ - length(q) + 0.5, 0.0, 1.0);
  }
  if (cover <= 0.0) discard;
  fragColor = vec4(vColor * cover, 0.0);
}
`,Ut=`#version 300 es
precision highp float;

uniform sampler2D tHome;
uniform sampler2D tSeed;
uniform sampler2D tOffset;
uniform sampler2D tVelocity;
uniform float uDt;
uniform float uReset;
uniform vec4 uBrush;
uniform float uBrushPower;
uniform vec4 uKick;

layout(location = 0) out vec4 outOffset;
layout(location = 1) out vec4 outVelocity;
${Rt}
${zt}
vec3 swirl(vec3 p) {
  float t = uDustTime * 0.15;
  vec3 a = vec3(1.7, 1.9, 1.5) * p.yzx + vec3(t, 1.2, 2.1);
  vec3 b = vec3(2.3, 2.1, 2.7) * p.zxy + vec3(0.4, t * 1.3, 0.9);
  vec3 ca = cos(a) * vec3(1.7, 1.9, 1.5);
  vec3 cb = cos(b) * vec3(2.3, 2.1, 2.7);
  return vec3(ca.z - cb.x, cb.y - ca.x, ca.y - cb.z);
}

void main() {
  ivec2 cell = ivec2(gl_FragCoord.xy);
  if (uReset > 0.5) {
    outOffset = vec4(0.0);
    outVelocity = vec4(0.0);
    return;
  }
  uint id = uint(cell.y * ${X} + cell.x);
  vec4 home = texelFetch(tHome, cell, 0);
  vec4 seed = texelFetch(tSeed, cell, 0);
  vec3 o = texelFetch(tOffset, cell, 0).xyz;
  vec3 v = texelFetch(tVelocity, cell, 0).xyz;
  float life;
  float spread;
  vec3 base = drift(home, seed, id, life, spread);
  vec3 p = base + o;

  float k = mix(0.8, 2.2, random(id * 7u + 11u));
  vec3 acc = -k * o - 1.5 * sqrt(k) * v;

  vec2 gap = p.xy - uBrush.xy;
  float touch = exp(-dot(gap, gap) / 0.07) * uBrushPower;
  acc += (vec3(uBrush.zw, 0.0) - v) * touch * 14.0;
  float pace = length(v);
  if (pace > 1e-4) {
    vec3 heading = v / pace;
    vec3 curl = swirl(p * 1.6);
    acc += (curl - heading * dot(curl, heading)) * min(pace, 2.0) * 1.8;
  }

  if (uKick.z > 0.0) {
    vec3 jolt = vec3(random(id * 7u + 12u), random(id * 7u + 13u), random(id * 7u + 14u)) - 0.5;
    float near = exp(-dot(p.xy - uKick.xy, p.xy - uKick.xy) / 0.4);
    vec3 spinKick = vec3(-p.z, 0.0, p.x) * 0.9;
    vec3 lift = vec3(0.0, 0.5 + 0.8 * random(id * 7u + 15u), 0.0) * (0.3 + 0.7 * smoothstep(0.2, -0.8, p.y));
    v += (jolt * 0.8 + spinKick + lift) * uKick.z * (0.4 + 0.45 * near);
  }

  v += acc * uDt;
  o += v * uDt;
  vec3 q = base + o;
  float len = length(q);
  if (len > 0.97) {
    vec3 n = q / len;
    o -= n * (len - 0.97);
    v -= n * max(dot(v, n), 0.0) * 1.5;
  }
  outOffset = vec4(o, 1.0);
  outVelocity = vec4(v, 1.0);
}
`,Wt=`#version 300 es
precision highp float;

uniform sampler2D tScene;
uniform float uLight;
uniform float uDecode;

in vec2 vUv;
out vec4 fragColor;

vec3 soften(vec3 x) {
  vec3 over = max(x - 0.6, 0.0);
  return min(x, 0.6) + 0.4 * (1.0 - exp(-over / 0.4));
}

void main() {
  vec4 scene = texture(tScene, vUv) * uDecode;
  vec3 light = max(scene.rgb, 0.0);
  float peak = max(light.r, max(light.g, light.b));
  if (uLight > 0.5) {
    vec3 hue = light / max(peak, 1e-4);
    float cover = 1.0 - exp(-peak * 2.4);
    vec3 ink = hue * mix(0.92, 0.72, cover);
    float core = clamp(scene.a * 0.7, 0.0, 1.0) * cover;
    vec3 tint = mix(vec3(1.0), hue, 0.22);
    fragColor = vec4(tint * core + ink * cover * (1.0 - core), core + cover * (1.0 - core));
    return;
  }
  light += vec3(max(peak - 1.8, 0.0) * 0.25);
  vec3 shown = soften(light);
  fragColor = vec4(shown, max(shown.r, max(shown.g, shown.b)));
}
`,Gt=({preset:e=`plasma`,color:t,theme:n=`dark`,size:r=.7,strands:i,crackle:a,flares:o,glow:s,sparks:c,particleCount:l,fill:u,motion:d,particleShape:f,depth:p,sway:m,twinkle:h,haze:g,speed:_=1,dustSpeed:v,interactive:y=!0,hoverStrength:b=.7,intro:x=!0,paused:S=!1,className:C=``,style:w,onFrame:T})=>{let E=(0,ut.useRef)(null),D=(0,ut.useRef)(null),O=(0,ut.useRef)(null),k=ft[e]||ft.plasma,A=(e,t)=>e??k[t],j=A(t,`color`),ee=(0,ut.useMemo)(()=>{let e=n===`light`;return{light:e,palette:Nt(Et(j,[.95,.36,.82]),e)}},[j,n]);return(0,ut.useEffect)(()=>{D.current={...ee,size:r,strands:A(i,`strands`),crackle:A(a,`crackle`),flares:A(o,`flares`),glow:A(s,`glow`),sparks:A(c,`sparks`),particleCount:A(l,`particleCount`),fill:A(u,`fill`),motion:A(d,`motion`),particleShape:A(f,`particleShape`),depth:A(p,`depth`),sway:A(m,`sway`),twinkle:A(h,`twinkle`),haze:A(g,`haze`),dustSpeed:A(v,`dustSpeed`),speed:_,interactive:y,hoverStrength:b,intro:x,paused:S,onFrame:T},O.current?.()}),(0,ut.useEffect)(()=>{let e=E.current;if(!e)return;let t=document.createElement(`canvas`),n={alpha:!0,premultipliedAlpha:!0,antialias:!1,depth:!1,preserveDrawingBuffer:!!T};if(!t.getContext(`webgl2`,n))return;let r=new ce({canvas:t,...n}),i=r.gl,a=i;t.style.display=`block`,t.style.width=`100%`,t.style.height=`100%`,t.setAttribute(`aria-hidden`,`true`),e.appendChild(t);let o=!!i.getExtension(`EXT_color_buffer_float`),s=o||!!i.getExtension(`EXT_color_buffer_half_float`),c=s?1:.25,l=new lt(i),u=new st(i),d=Ft(),f=new ct(i,{width:1,height:1,depth:!1,type:s?a.HALF_FLOAT:i.UNSIGNED_BYTE,format:i.RGBA,internalFormat:s?a.RGBA16F:i.RGBA,minFilter:i.NEAREST,magFilter:i.NEAREST}),p=Array(16).fill(0),m={uCenter:{value:[0,0]},uRadius:{value:1},uDpr:{value:1},uLine:{value:.6},uTime:{value:0},uFrame:{value:0},uBins:{value:420},uStrands:{value:5},uCrackle:{value:.6},uFlares:{value:.5},uGlow:{value:.8},uHaze:{value:.7},uFill:{value:.5},uPresence:{value:0},uUnfold:{value:0},uBloom:{value:0},uInside:{value:0},uEncode:{value:c},uRim:{value:[1,1,1]},uRimHot:{value:[1,1,1]},uRimMid:{value:[1,1,1]},uRimDeep:{value:[1,1,1]},uSpark:{value:[1,1,1]},uSparkGlow:{value:[1,1,1]},uHazeColor:{value:[0,0,0]},uEdgeColor:{value:[0,0,0]},uHeat:{value:[0,0,0,0]},uHarmonics:{value:d.harmonics},uRates:{value:d.rates},uPhases:{value:d.phases},uFlareHarmonics:{value:d.flareHarmonics},uFlareRates:{value:d.flareRates},uFlarePhases:{value:d.flarePhases},uArcs:{value:p}},h={uDustTime:{value:0},uTurn:{value:[0,0]},uMotion:{value:0},uFill:m.uFill,tHome:{value:u},tSeed:{value:u}},g={...h,tOffset:{value:u},uStirred:{value:0},uCenter:m.uCenter,uViewport:{value:[1,1]},uRadius:m.uRadius,uDpr:m.uDpr,uDepth:{value:.6},uTwinkle:{value:.5},uPointScale:{value:1},uReveal:{value:0},uEncode:{value:c},uTones:{value:Array(15).fill(1)},uRimTone:{value:[1,1,1]},uShape:{value:0}},_={...h,tOffset:{value:u},tVelocity:{value:u},uDt:{value:.016},uReset:{value:1},uBrush:{value:[0,0,0,0]},uBrushPower:{value:0},uKick:{value:[0,0,0,0]}},v={tScene:{value:f.texture},uLight:{value:0},uDecode:{value:1/c}},y=e=>(e.setBlendFunc(i.ONE,i.ONE),e),b=new rt(i,{geometry:l,program:y(new ne(i,{vertex:Lt,fragment:Bt,uniforms:m,transparent:!0,depthTest:!1,depthWrite:!1}))}),x=y(new ne(i,{vertex:Vt,fragment:Ht,uniforms:g,transparent:!0,depthTest:!1,depthWrite:!1})),S=s?new rt(i,{geometry:l,program:new ne(i,{vertex:Lt,fragment:Ut,uniforms:_,depthTest:!1,depthWrite:!1})}):null,C=new rt(i,{geometry:l,program:new ne(i,{vertex:Lt,fragment:Wt,uniforms:v,depthTest:!1,depthWrite:!1})}),w=e=>{e&&(i.deleteFramebuffer(e.buffer),e.textures.forEach(e=>i.deleteTexture(e.texture)))},k=e=>new ct(i,{width:X,height:e,color:2,depth:!1,type:o?i.FLOAT:a.HALF_FLOAT,format:i.RGBA,internalFormat:o?a.RGBA32F:a.RGBA16F,minFilter:i.NEAREST,magFilter:i.NEAREST}),A=(e,t)=>new st(i,{image:e,width:X,height:t,type:i.FLOAT,format:i.RGBA,internalFormat:a.RGBA32F,minFilter:i.NEAREST,magFilter:i.NEAREST,generateMipmaps:!1,flipY:!1}),j=null,ee=()=>{j&&=(j.mesh.geometry.remove(),i.deleteTexture(j.home.texture),i.deleteTexture(j.seed.texture),w(j.read),w(j.write),null)},te=()=>{S&&j&&j.read&&j.write&&(_.tOffset.value=u,_.tVelocity.value=u,_.uReset.value=1,r.render({scene:S,target:j.read,clear:!1}),r.render({scene:S,target:j.write,clear:!1}),_.uReset.value=0)},re=e=>{let t=Z(Math.round(e/100)*100,0,_t);if(j&&j.requested===t)return;if(ee(),!t){j=null;return}let n=It(t),r=new Float32Array(n.count);for(let e=0;e<n.count;e++)r[e]=e;let a=new M(i,{aIndex:{size:1,data:r}});j={requested:t,rows:n.rows,home:A(n.home,n.rows),seed:A(n.seed,n.rows),mesh:new rt(i,{mode:i.POINTS,geometry:a,program:x}),read:S?k(n.rows):null,write:S?k(n.rows):null},h.tHome.value=j.home,h.tSeed.value=j.seed,te(),z=0},ie=window.matchMedia?.(`(prefers-reduced-motion: reduce)`).matches??!1,N=Pt(913),P=1,F=1,I=0,ae=performance.now(),oe=0,se=0,le=0,L=0,ue=!0,de=!0,R=0,z=0,fe=0,B=null,pe=.3,V=[],H={x:0,y:0,inside:!1,fresh:!0},U={angle:0,velocity:0,power:0,near:0},W={x:0,y:0,vx:0,vy:0},G={x:0,y:0,vx:0,vy:0},me=!1,he=()=>{P=Math.max(1,e.clientWidth),F=Math.max(1,e.clientHeight),r.dpr=Math.min(window.devicePixelRatio||1,2,Math.sqrt(vt/(P*F))),r.setSize(P,F),f.setSize(i.canvas.width,i.canvas.height)},ge=()=>{me=!0,K()},_e=(e,t)=>{V.length>=gt||V.push({start:e,span:(.05+N()*.07)*(N()<.5?-1:1),curl:.02+N()*.04,life:0,duration:.2+N()*.2,drift:(N()-.5)*.3,strength:t})},ve=e=>{if(I=0,me&&(me=!1,he()),!de)return;let n=D.current,a=Math.min(.05,Math.max(1/240,(e-ae)/1e3));if(ae=e,!n)return;let o=!n.paused&&!ie;L=n.intro&&!ie?Math.min(1,L+a/yt):1;let s=Ct(Q(0,.42,L)),c=Ct(Q(0,.32,L)),l=Math.sin(Math.PI*Q(.22,.78,L))*.35,d=Math.max(8,Z(n.size,.1,1.5)*Math.min(P,F)/2),y=n.interactive&&!ie?Z(n.hoverStrength,0,1):0,x=H.x-P/2,w=F/2-H.y,T=Math.hypot(x,w),E=H.inside?y:0;U.power<.02&&(U.angle=Math.atan2(w,x),U.velocity=0);let O=Tt(Math.atan2(w,x)-U.angle);U.velocity+=(120*O-19*U.velocity)*a,U.angle=Tt(U.angle+U.velocity*a),U.power+=(E-U.power)*(1-Math.exp(-a/(E>U.power?.3:.55)));let k=Math.exp(-(((T-d)/(d*.45))**2));U.near+=(k-U.near)*(1-Math.exp(-a/.15)),R*=Math.exp(-a/.7);let A=x/d,M=w/d;Math.hypot(A-W.x,M-W.y)>.6&&(H.fresh=!0),H.fresh&&=(W.x=A,W.y=M,W.vx=0,W.vy=0,!1);let ee=1-Math.exp(-a/.05);W.vx+=((A-W.x)/a-W.vx)*ee,W.vy+=((M-W.y)/a-W.vy)*ee,W.x=A,W.y=M;let ne=Math.hypot(W.vx,W.vy),ce=ne>4?4/ne:1,ge=Math.exp(-Math.max(0,Math.hypot(A,M)-1)*6),K=H.inside?y*ge*s:0;if(fe=fe*Math.exp(-a/1.2)+K*Math.min(ne,4)*a,o){let e=1+R*.6+U.power*U.near*.3,t=a*Math.max(0,n.speed)*2*e;oe+=t,se+=a*Math.max(0,n.dustSpeed)*(1+R*.4),le+=a*Math.max(0,n.dustSpeed);let r=Z(n.crackle+R*.5,0,1.5);if(n.sparks>.01&&L>.55&&(pe-=t*n.sparks*2*(.6+r*.6),pe<=0)){let e=U.power*U.near,t=N()<e*.7?U.angle+(N()-.5)*.8:N()<.7?Math.PI/2+(N()-.5)*1.5:N()*Math.PI*2;_e(t,.8+e*.6+R*.4),pe=.15+N()*.6}for(let e=V.length-1;e>=0;e--){let n=V[e];n.life+=t,n.start+=n.drift*t,n.life>=n.duration&&V.splice(e,1)}}else V.length=0;for(let e=0;e<gt;e++){let t=V[e];p[e*4]=t?t.start:0,p[e*4+1]=t?t.span:0,p[e*4+2]=t?t.curl:0,p[e*4+3]=t?Math.sin(Math.PI*t.life/t.duration)*t.strength:0}re(n.particleCount);let q=n.palette;m.uCenter.value=[P/2,F/2],m.uRadius.value=d,m.uDpr.value=r.dpr,m.uLine.value=Math.max(.6,d*.0035),m.uTime.value=oe,m.uFrame.value=Math.floor(oe*24)%1e5,m.uBins.value=Z(Math.round(Math.PI*2*d/2.6),240,900),m.uStrands.value=Math.round(Z(n.strands,1,ht)),m.uCrackle.value=Z(n.crackle,0,1)+R*.5+l,m.uFlares.value=Z(n.flares,0,1),m.uGlow.value=Z(n.glow,0,2)*(1+R*.5+l)*(n.light?.35:1),m.uHaze.value=Z(n.haze,0,2)*(n.light?.6:1),m.uFill.value=Z(n.fill,0,1),m.uPresence.value=s,m.uUnfold.value=c,m.uBloom.value=s*s,m.uInside.value=Q(.2,.95,L),m.uRim.value=q.rim,m.uRimHot.value=q.rimHot,m.uRimMid.value=q.rimMid,m.uRimDeep.value=q.rimDeep,m.uSpark.value=q.spark,m.uSparkGlow.value=q.sparkGlow,m.uHazeColor.value=q.haze,m.uEdgeColor.value=q.edge,m.uHeat.value=[U.angle,U.near,U.power*s,0],h.uDustTime.value=se;let ye=H.inside?y*s:0,be=Z(A,-1.6,1.6)*ye,J=Z(M,-1.6,1.6)*ye;G.vx+=(40*(be-G.x)-11*G.vx)*a,G.vy+=(40*(J-G.y)-11*G.vy)*a,G.x+=G.vx*a,G.y+=G.vy*a;let xe=Z(n.sway,0,1);h.uTurn.value=[xe*.42*Math.sin(le*.23)+G.x*.3,xe*.12*Math.sin(le*.17+1.3)-G.y*.16],h.uMotion.value=pt[n.motion]??0,g.uViewport.value=[P,F],g.uDepth.value=Z(n.depth,0,1),g.uTwinkle.value=Z(n.twinkle,0,1),g.uPointScale.value=Math.max(1,d/491),g.uReveal.value=Q(.18,1,L),g.uTones.value=q.tones.flat(),g.uRimTone.value=q.rim,g.uShape.value=mt[n.particleShape]??0;let Y=j;Y&&S&&(fe>.002||B)&&(z=bt);let Se=!1;if(Y&&Y.read&&Y.write&&S&&z>0){_.uDt.value=Math.min(a,1/30),_.uBrush.value=[W.x,W.y,W.vx*ce,W.vy*ce],_.uBrushPower.value=K,_.uKick.value=B?[B.x,B.y,B.strength,0]:[0,0,0,0],_.tOffset.value=Y.read.textures[0]??u,_.tVelocity.value=Y.read.textures[1]??u,r.render({scene:S,target:Y.write,clear:!1});let e=Y.read;Y.read=Y.write,Y.write=e,z-=a,Se=z>0,Se||(z=0,te())}B=null,g.uStirred.value=+!!Se,g.tOffset.value=Y&&Y.read?Y.read.textures[0]??u:u,i.clearColor(0,0,0,0),r.render({scene:b,target:f,clear:!0}),j&&r.render({scene:j.mesh,target:f,clear:!1}),v.uLight.value=+!!n.light,r.render({scene:C,clear:!1}),n.onFrame?.(t);let Ce=Math.abs(E-U.power)>.002||R>.002||z>0||Math.abs(U.velocity)>.01||Math.hypot(G.vx,G.vy,G.x-be,G.y-J)>.001;ue&&(o||L<1||Ce)&&(I=requestAnimationFrame(ve))},K=()=>{!I&&ue&&de&&(ae=performance.now(),I=requestAnimationFrame(ve))},q=t=>{let n=e.getBoundingClientRect(),r=t.clientX-n.left,i=t.clientY-n.top;return{x:r,y:i,inside:r>=0&&i>=0&&r<=n.width&&i<=n.height}},ye=e=>{let t=q(e);t.inside&&!H.inside&&(H.fresh=!0),H.x=t.x,H.y=t.y,H.inside=t.inside,t.inside&&K()},be=e=>{let t=D.current,n=q(e);if(!t||!t.interactive||ie||!n.inside)return;H.inside||(H.fresh=!0),H.x=n.x,H.y=n.y,H.inside=!0;let r=Math.max(8,Z(t.size,.1,1.5)*Math.min(P,F)/2),i=(n.x-P/2)/r,a=(F/2-n.y)/r;if(Math.hypot(i,a)>1.3)return;let o=Z(t.hoverStrength,0,1);B={x:i,y:a,strength:o*1.2},R=Math.max(R,o);let s=Math.atan2(a,i);_e(s+(N()-.5)*.5,1.3),_e(s+Math.PI+(N()-.5)*1.2,1.1),K()},J=()=>{H.inside=!1,K()},xe=e=>{e.relatedTarget||J()},Y=e=>{e.pointerType===`touch`&&J()},Se=()=>{document.hidden||K()};window.addEventListener(`pointermove`,ye,{passive:!0}),window.addEventListener(`pointerdown`,be,{passive:!0}),window.addEventListener(`pointerout`,xe,{passive:!0}),window.addEventListener(`pointerup`,Y,{passive:!0}),window.addEventListener(`blur`,J),document.addEventListener(`visibilitychange`,Se);let Ce=new ResizeObserver(ge);Ce.observe(e);let we=new IntersectionObserver(([e])=>{ue=!!e?.isIntersecting,K()});return we.observe(e),O.current=K,ge(),()=>{de=!1,ue=!1,cancelAnimationFrame(I),Ce.disconnect(),we.disconnect(),window.removeEventListener(`pointermove`,ye),window.removeEventListener(`pointerdown`,be),window.removeEventListener(`pointerout`,xe),window.removeEventListener(`pointerup`,Y),window.removeEventListener(`blur`,J),document.removeEventListener(`visibilitychange`,Se),O.current=null,ee(),w(f),i.getExtension(`WEBGL_lose_context`)?.loseContext(),t.parentNode&&t.parentNode.removeChild(t)}},[]),(0,dt.jsx)(`div`,{ref:E,className:`crystalized-ball ${C}`.trim(),style:w})};export{Gt as default};